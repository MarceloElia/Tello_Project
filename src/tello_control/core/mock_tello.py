"""
mock_tello.py

Ein Software-Ersatz für die echte Tello-Drohne.

Der Mock bildet die wichtigsten Methoden von djitellopy.Tello nach, fliegt aber
nichts: Stattdessen führt er eine simulierte 3D-Position (x, y, z in cm) und die
Blickrichtung (yaw in Grad) mit, protokolliert jeden Befehl und prüft ihn gegen
die Grenzen des echten Tello-SDK. So testest du deine komplette Steuerlogik
(Gesten, Sprache) am Schreibtisch, bevor die echte Drohne überhaupt anläuft.

Koordinaten (Vogelperspektive):
    Y = vorwärts ab Startrichtung (auf der Karte nach oben)
    X = rechts ab Startrichtung   (auf der Karte nach rechts)
    Z = Höhe
    yaw = Blickrichtung im Uhrzeigersinn, 0 = Startrichtung
"""

import math
import time

from tello_control.core.constants import (
    DIST_MIN, DIST_MAX, ANGLE_MIN, ANGLE_MAX, RC_MIN, RC_MAX,
)

# Nominale Umrechnung RC-Wert (−100..100) → Bewegung pro Sekunde, damit der Mock
# bei gehaltener Geschwindigkeit eine plausible Pose integriert (nur Logik, keine
# Physik). Die echte Drohne integriert selbst; der Sim macht es über PID.
_RC_CM_PER_S  = 1.0     # 1 cm/s pro RC-Einheit  → RC 40 ≈ 40 cm/s
_RC_DEG_PER_S = 1.0     # 1 °/s  pro RC-Einheit  → yaw 40 ≈ 40 °/s


class TelloException(Exception):
    """Entspricht grob dem Fehler, den die echte Tello bei ungültigen Befehlen wirft."""
    pass


class MockTello:

    def __init__(self, verbose: bool = True, start_battery: int = 86) -> None:
        self.verbose = verbose
        self.connected = False
        self.flying = False
        self.battery = start_battery     # Startwert wie bei deiner echten Drohne
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.yaw = 0.0                   # Grad
        self.log: list[dict] = []        # Liste protokollierter Befehle
        self._t0: float | None = None
        self._rc = (0, 0, 0, 0)          # gehaltener RC-Sollwert (lr, fb, ud, yaw)
        self._rc_t: float | None = None  # monotone Zeit des letzten tick() (RC)

    # ---------- interne Helfer ----------
    def _elapsed(self) -> float:
        return 0.0 if self._t0 is None else round(time.time() - self._t0, 2)

    def _record(self, command: str) -> None:
        self.log.append({
            "t": self._elapsed(), "cmd": command,
            "x": round(self.x), "y": round(self.y),
            "z": round(self.z), "yaw": round(self.yaw) % 360,
        })

    def _say(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _check_connected(self) -> None:
        if not self.connected:
            raise TelloException("Nicht verbunden. Erst connect() aufrufen.")

    def _check_flying(self, action: str) -> None:
        if not self.flying:
            raise TelloException(f"'{action}' nicht möglich: Drohne ist nicht in der Luft.")

    def _check_dist(self, cm: int) -> None:
        if not (DIST_MIN <= cm <= DIST_MAX):
            raise TelloException(
                f"Distanz {cm} cm außerhalb des erlaubten Bereichs "
                f"({DIST_MIN}-{DIST_MAX} cm)."
            )

    def _check_angle(self, deg: int) -> None:
        if not (ANGLE_MIN <= deg <= ANGLE_MAX):
            raise TelloException(
                f"Winkel {deg}° außerhalb des erlaubten Bereichs "
                f"({ANGLE_MIN}-{ANGLE_MAX}°)."
            )

    def _drain(self, amount: int = 1) -> None:
        self.battery = max(0, self.battery - amount)

    def _after_move(self) -> None:
        """Hook nach jedem diskreten move_*/rotate_* (Template-Method).

        Basis: No-Op. ``PyBulletBackend`` überschreibt ihn und treibt die Physik
        zur soeben gesetzten Logik-Pose nach — so muss die Sim keine acht
        Flugmethoden nachbauen, sie hängt sich nur an diesen einen Punkt.
        """

    # ---------- API wie djitellopy.Tello ----------
    def connect(self) -> None:
        self.connected = True
        self._t0 = time.time()
        self._say("🔌 Mock-Drohne verbunden.")
        self._record("connect")

    def get_battery(self) -> int:
        return self.battery

    def get_height(self) -> int:
        return round(self.z)

    def takeoff(self) -> None:
        self._check_connected()
        self.flying = True
        self.z = 100                     # echte Tello steigt auf ~1 m
        self._drain(2)
        self._say(f"🛫 Takeoff  →  Höhe {self.z:.0f} cm")
        self._record("takeoff")

    def land(self) -> None:
        self._check_flying("land")
        self.z = 0
        self.flying = False
        self._drain(1)
        self._say(f"🛬 Landung   →  {self.position_str()}")
        self._record("land")

    def emergency(self) -> None:
        self.flying = False
        self._say("⛔ NOT-STOPP: Motoren sofort aus.")
        self._record("emergency")

    # Translation relativ zur aktuellen Blickrichtung
    def _translate(self, forward: float = 0, right: float = 0, up: float = 0) -> None:
        rad = math.radians(self.yaw)
        self.x += forward * math.sin(rad) + right * math.cos(rad)
        self.y += forward * math.cos(rad) - right * math.sin(rad)
        self.z += up

    # Die acht diskreten Manöver teilen sich denselben Ablauf (Check → Translation
    # → Akku → Log → Hook); nur Achse/Vorzeichen/Label unterscheiden sich. Statt
    # den Ablauf achtmal zu kopieren, bündeln ihn zwei Helfer — die öffentlichen
    # Methoden bleiben aber einzeln stehen (grep-/IDE-sichtbar, anders als eine
    # dynamisch erzeugte Methodenliste).
    def _linear_move(self, action: str, icon: str, label: str, cm: int,
                     *, forward: float = 0, right: float = 0, up: float = 0) -> None:
        self._check_flying(action)
        self._check_dist(cm)
        self._translate(forward=forward, right=right, up=up)
        self._drain()
        self._say(f"{icon}  {label} {cm} cm  →  {self.position_str()}")
        self._record(f"{label} {cm}")
        self._after_move()

    def _rotate(self, action: str, icon: str, label: str, deg: int, *, sign: int) -> None:
        self._check_flying(action)
        self._check_angle(deg)
        self.yaw = (self.yaw + sign * deg) % 360
        self._drain()
        self._say(f"{icon}  rotate {label} {deg}°  →  yaw {self.yaw:.0f}°")
        self._record(f"{label} {deg}")
        self._after_move()

    def move_forward(self, cm: int) -> None:
        self._linear_move("move_forward", "⬆️", "forward", cm, forward=cm)

    def move_back(self, cm: int) -> None:
        self._linear_move("move_back", "⬇️", "back", cm, forward=-cm)

    def move_right(self, cm: int) -> None:
        self._linear_move("move_right", "➡️", "right", cm, right=cm)

    def move_left(self, cm: int) -> None:
        self._linear_move("move_left", "⬅️", "left", cm, right=-cm)

    def move_up(self, cm: int) -> None:
        self._linear_move("move_up", "🔼", "up", cm, up=cm)

    def move_down(self, cm: int) -> None:
        self._linear_move("move_down", "🔽", "down", cm, up=-cm)

    def rotate_clockwise(self, deg: int) -> None:
        self._rotate("rotate_clockwise", "↻", "cw", deg, sign=+1)

    def rotate_counter_clockwise(self, deg: int) -> None:
        self._rotate("rotate_counter_clockwise", "↺", "ccw", deg, sign=-1)

    # ---------- RC-/Geschwindigkeitssteuerung ----------
    def send_rc_control(self, lr: int, fb: int, ud: int, yaw: int) -> None:
        """Gehaltener Geschwindigkeits-Sollwert (wie djitellopy). Nicht blockierend.

        Werte werden auf den SDK-Bereich geklemmt und gespeichert; die Pose wird
        erst in tick() über die verstrichene Zeit integriert. Kein Akku-Abzug pro
        Aufruf – es ist ein gehaltener Zustand, kein diskretes Manöver.
        """
        self._check_flying("send_rc_control")

        def clamp(v: int) -> int:
            return max(RC_MIN, min(RC_MAX, int(v)))

        self._rc = (clamp(lr), clamp(fb), clamp(ud), clamp(yaw))

    def tick(self, dt: float | None = None) -> None:
        """Integriert den gehaltenen RC-Sollwert in die Pose.

        dt = Sekunden seit dem letzten tick(); ohne Angabe aus der monotonen Uhr.
        Tests übergeben ein festes dt für Determinismus. No-Op solange am Boden.
        """
        now = time.monotonic()
        if dt is None:
            dt = 0.0 if self._rc_t is None else (now - self._rc_t)
        self._rc_t = now
        if not self.flying or dt <= 0:
            return
        lr, fb, ud, yaw = self._rc
        self._translate(
            forward=fb * _RC_CM_PER_S * dt,
            right=lr * _RC_CM_PER_S * dt,
            up=ud * _RC_CM_PER_S * dt,
        )
        self.yaw = (self.yaw + yaw * _RC_DEG_PER_S * dt) % 360

    def end(self) -> None:
        self._say("🔌 Verbindung beendet.")

    @property
    def is_flying(self) -> bool:
        """Alias matching djitellopy.Tello's attribute name — keeps interface consistent."""
        return self.flying

    # ---------- Auswertung ----------
    def pose(self) -> tuple[float, float, float, float]:
        """Aktuelle simulierte Pose: (x, y, z in cm, yaw in Grad).

        Gekapselter Zugriff für den Controller — der greift so nicht mehr direkt
        auf die Felder x/y/z/yaw zu (siehe PoseBackend-Protokoll).
        """
        return (self.x, self.y, self.z, self.yaw)

    def position_str(self) -> str:
        return f"x={self.x:.0f}  y={self.y:.0f}  z={self.z:.0f}  yaw={self.yaw:.0f}°"

    def print_log(self) -> None:
        print("\n  Befehlsprotokoll")
        print("  " + "-" * 52)
        print(f"  {'t/s':>5}  {'Befehl':<14}{'x':>6}{'y':>6}{'z':>6}{'yaw':>6}")
        print("  " + "-" * 52)
        for e in self.log:
            print(f"  {e['t']:>5}  {e['cmd']:<14}{e['x']:>6}{e['y']:>6}{e['z']:>6}{e['yaw']:>6}")
        print("  " + "-" * 52)
        print(f"  Endposition: {self.position_str()}   Akku: {self.battery}%\n")

    def print_map(self, width: int = 39, height: int = 17) -> None:
        """Zeichnet die Flugbahn von oben (X nach rechts, Y nach oben)."""
        pts = [(e["x"], e["y"]) for e in self.log if e["cmd"] not in ("connect",)]
        if len(pts) < 2:
            return
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        spanx = max(maxx - minx, 1)
        spany = max(maxy - miny, 1)
        grid = [[" "] * width for _ in range(height)]

        def to_cell(x: float, y: float) -> tuple[int, int]:
            cx = int((x - minx) / spanx * (width - 1))
            cy = int((y - miny) / spany * (height - 1))
            return cx, (height - 1 - cy)   # y oben

        for x, y in pts:
            cx, cy = to_cell(x, y)
            grid[cy][cx] = "·"
        sx, sy = to_cell(*pts[0])
        grid[sy][sx] = "S"
        ex, ey = to_cell(*pts[-1])
        grid[ey][ex] = "E"

        print("  Flugbahn von oben  (S = Start, E = Ende)")
        print("  +" + "-" * width + "+")
        for row in grid:
            print("  |" + "".join(row) + "|")
        print("  +" + "-" * width + "+")
        print(f"  X: {minx:.0f}…{maxx:.0f} cm    Y: {miny:.0f}…{maxy:.0f} cm\n")
