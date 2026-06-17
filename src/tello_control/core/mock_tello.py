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

from tello_control.core.constants import DIST_MIN, DIST_MAX, ANGLE_MIN, ANGLE_MAX


class TelloException(Exception):
    """Entspricht grob dem Fehler, den die echte Tello bei ungültigen Befehlen wirft."""
    pass


class MockTello:

    def __init__(self, verbose=True, start_battery=86):
        self.verbose = verbose
        self.connected = False
        self.flying = False
        self.battery = start_battery     # Startwert wie bei deiner echten Drohne
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        self.yaw = 0.0                   # Grad
        self.log = []                    # Liste protokollierter Befehle
        self._t0 = None

    # ---------- interne Helfer ----------
    def _elapsed(self):
        return 0.0 if self._t0 is None else round(time.time() - self._t0, 2)

    def _record(self, command):
        self.log.append({
            "t": self._elapsed(), "cmd": command,
            "x": round(self.x), "y": round(self.y),
            "z": round(self.z), "yaw": round(self.yaw) % 360,
        })

    def _say(self, msg):
        if self.verbose:
            print(msg)

    def _check_connected(self):
        if not self.connected:
            raise TelloException("Nicht verbunden. Erst connect() aufrufen.")

    def _check_flying(self, action):
        if not self.flying:
            raise TelloException(f"'{action}' nicht möglich: Drohne ist nicht in der Luft.")

    def _check_dist(self, cm):
        if not (DIST_MIN <= cm <= DIST_MAX):
            raise TelloException(
                f"Distanz {cm} cm außerhalb des erlaubten Bereichs "
                f"({DIST_MIN}-{DIST_MAX} cm)."
            )

    def _check_angle(self, deg):
        if not (ANGLE_MIN <= deg <= ANGLE_MAX):
            raise TelloException(
                f"Winkel {deg}° außerhalb des erlaubten Bereichs "
                f"({ANGLE_MIN}-{ANGLE_MAX}°)."
            )

    def _drain(self, amount=1):
        self.battery = max(0, self.battery - amount)

    # ---------- API wie djitellopy.Tello ----------
    def connect(self):
        self.connected = True
        self._t0 = time.time()
        self._say("🔌 Mock-Drohne verbunden.")
        self._record("connect")

    def get_battery(self):
        return self.battery

    def get_height(self):
        return round(self.z)

    def takeoff(self):
        self._check_connected()
        self.flying = True
        self.z = 100                     # echte Tello steigt auf ~1 m
        self._drain(2)
        self._say(f"🛫 Takeoff  →  Höhe {self.z:.0f} cm")
        self._record("takeoff")

    def land(self):
        self._check_flying("land")
        self.z = 0
        self.flying = False
        self._drain(1)
        self._say(f"🛬 Landung   →  {self.position_str()}")
        self._record("land")

    def emergency(self):
        self.flying = False
        self._say("⛔ NOT-STOPP: Motoren sofort aus.")
        self._record("emergency")

    # Translation relativ zur aktuellen Blickrichtung
    def _translate(self, forward=0, right=0, up=0):
        rad = math.radians(self.yaw)
        self.x += forward * math.sin(rad) + right * math.cos(rad)
        self.y += forward * math.cos(rad) - right * math.sin(rad)
        self.z += up

    def move_forward(self, cm):
        self._check_flying("move_forward"); self._check_dist(cm)
        self._translate(forward=cm); self._drain()
        self._say(f"⬆️  forward {cm} cm  →  {self.position_str()}")
        self._record(f"forward {cm}")

    def move_back(self, cm):
        self._check_flying("move_back"); self._check_dist(cm)
        self._translate(forward=-cm); self._drain()
        self._say(f"⬇️  back {cm} cm  →  {self.position_str()}")
        self._record(f"back {cm}")

    def move_right(self, cm):
        self._check_flying("move_right"); self._check_dist(cm)
        self._translate(right=cm); self._drain()
        self._say(f"➡️  right {cm} cm  →  {self.position_str()}")
        self._record(f"right {cm}")

    def move_left(self, cm):
        self._check_flying("move_left"); self._check_dist(cm)
        self._translate(right=-cm); self._drain()
        self._say(f"⬅️  left {cm} cm  →  {self.position_str()}")
        self._record(f"left {cm}")

    def move_up(self, cm):
        self._check_flying("move_up"); self._check_dist(cm)
        self._translate(up=cm); self._drain()
        self._say(f"🔼 up {cm} cm  →  {self.position_str()}")
        self._record(f"up {cm}")

    def move_down(self, cm):
        self._check_flying("move_down"); self._check_dist(cm)
        self._translate(up=-cm); self._drain()
        self._say(f"🔽 down {cm} cm  →  {self.position_str()}")
        self._record(f"down {cm}")

    def rotate_clockwise(self, deg):
        self._check_flying("rotate_clockwise"); self._check_angle(deg)
        self.yaw = (self.yaw + deg) % 360; self._drain()
        self._say(f"↻  rotate cw {deg}°  →  yaw {self.yaw:.0f}°")
        self._record(f"cw {deg}")

    def rotate_counter_clockwise(self, deg):
        self._check_flying("rotate_counter_clockwise"); self._check_angle(deg)
        self.yaw = (self.yaw - deg) % 360; self._drain()
        self._say(f"↺  rotate ccw {deg}°  →  yaw {self.yaw:.0f}°")
        self._record(f"ccw {deg}")

    def end(self):
        self._say("🔌 Verbindung beendet.")

    @property
    def is_flying(self) -> bool:
        """Alias matching djitellopy.Tello's attribute name — keeps interface consistent."""
        return self.flying

    # ---------- Auswertung ----------
    def position_str(self):
        return f"x={self.x:.0f}  y={self.y:.0f}  z={self.z:.0f}  yaw={self.yaw:.0f}°"

    def print_log(self):
        print("\n  Befehlsprotokoll")
        print("  " + "-" * 52)
        print(f"  {'t/s':>5}  {'Befehl':<14}{'x':>6}{'y':>6}{'z':>6}{'yaw':>6}")
        print("  " + "-" * 52)
        for e in self.log:
            print(f"  {e['t']:>5}  {e['cmd']:<14}{e['x']:>6}{e['y']:>6}{e['z']:>6}{e['yaw']:>6}")
        print("  " + "-" * 52)
        print(f"  Endposition: {self.position_str()}   Akku: {self.battery}%\n")

    def print_map(self, width=39, height=17):
        """Zeichnet die Flugbahn von oben (X nach rechts, Y nach oben)."""
        pts = [(e["x"], e["y"]) for e in self.log if e["cmd"] not in ("connect",)]
        if len(pts) < 2:
            return
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys)
        spanx = max(maxx - minx, 1); spany = max(maxy - miny, 1)
        grid = [[" "] * width for _ in range(height)]

        def to_cell(x, y):
            cx = int((x - minx) / spanx * (width - 1))
            cy = int((y - miny) / spany * (height - 1))
            return cx, (height - 1 - cy)   # y oben

        for x, y in pts:
            cx, cy = to_cell(x, y)
            grid[cy][cx] = "·"
        sx, sy = to_cell(*pts[0]); grid[sy][sx] = "S"
        ex, ey = to_cell(*pts[-1]); grid[ey][ex] = "E"

        print("  Flugbahn von oben  (S = Start, E = Ende)")
        print("  +" + "-" * width + "+")
        for row in grid:
            print("  |" + "".join(row) + "|")
        print("  +" + "-" * width + "+")
        print(f"  X: {minx:.0f}…{maxx:.0f} cm    Y: {miny:.0f}…{maxy:.0f} cm\n")
