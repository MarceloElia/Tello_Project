"""
tello_control.core.controller

Die Abstraktionsschicht zwischen deiner Steuerlogik (Gesten, Sprache) und der
Drohne. Deine restliche Anwendung redet NUR mit dieser Klasse und merkt nie, ob
dahinter der Mock oder die echte Tello steckt.

Umschalten zwischen Simulation und echtem Flug:
    controller = DroneController(simulated=True)    # Mock, läuft ohne Drohne
    controller = DroneController(simulated=False)   # echte Tello über WLAN

Sonst ändert sich an deinem Code nichts.
"""

from typing import cast

from tello_control.core.backend import DroneBackend, PoseBackend
from tello_control.core.mock_tello import MockTello


class DroneController:
    """
    Drei Backends:
        backend="mock" → MockTello       (reine Logik, kein WLAN, Standard)
        backend="sim"  → PyBulletBackend (Physik-Sim, 3D-Fenster, conda-Env tello-sim)
        backend="real" → djitellopy.Tello (echte Drohne über WLAN)

    Abwärtskompatibel: simulated=True → "mock", simulated=False → "real".
    """

    def __init__(self, backend: str | None = None, simulated: bool | None = None,
                 verbose: bool = True, backend_kwargs: dict | None = None) -> None:
        # Backend bestimmen (alte simulated-API weiter unterstützen)
        if backend is None:
            backend = "mock" if (simulated is None or simulated) else "real"
        if backend not in ("mock", "sim", "real"):
            raise ValueError(f"Unbekanntes Backend '{backend}'. Erlaubt: mock, sim, real.")

        self.backend = backend
        # mock UND sim führen Position mit → für position()/report() als "simuliert" behandeln
        self.simulated = backend in ("mock", "sim")
        kw = backend_kwargs or {}   # z.B. {"gui": True, "realtime": True} für sim

        self.drone: DroneBackend
        if backend == "mock":
            self.drone = MockTello(verbose=verbose, **kw)
        elif backend == "sim":
            # Nur bei Bedarf importieren – PyBullet lebt in der conda-Env tello-sim,
            # so läuft mock/real im normalen venv ohne installiertes PyBullet.
            from tello_control.sim.pybullet_backend import PyBulletBackend
            self.drone = PyBulletBackend(verbose=verbose, **kw)
        else:
            # djitellopy erst laden, wenn wirklich geflogen wird.
            from djitellopy import Tello
            self.drone = Tello()

    # ---- Verbindung & Status ----
    def connect(self) -> int:
        self.drone.connect()
        return self.battery()

    def battery(self) -> int:
        return self.drone.get_battery()

    def height(self) -> int:
        return self.drone.get_height()

    # ---- Flug ----
    def takeoff(self) -> None:
        self.drone.takeoff()

    def land(self) -> None:
        self.drone.land()

    def emergency(self) -> None:
        self.drone.emergency()

    # ---- Bewegung (klare, kurze Namen für deine Steuerlogik) ----
    def forward(self, cm: int) -> None:  self.drone.move_forward(cm)
    def back(self, cm: int) -> None:     self.drone.move_back(cm)
    def left(self, cm: int) -> None:     self.drone.move_left(cm)
    def right(self, cm: int) -> None:    self.drone.move_right(cm)
    def up(self, cm: int) -> None:       self.drone.move_up(cm)
    def down(self, cm: int) -> None:     self.drone.move_down(cm)
    def rotate_cw(self, deg: int) -> None:  self.drone.rotate_clockwise(deg)
    def rotate_ccw(self, deg: int) -> None: self.drone.rotate_counter_clockwise(deg)

    def send_rc_control(self, lr: int, fb: int, ud: int, yaw: int) -> None:
        """Nicht-blockierende Geschwindigkeitssteuerung (RC). Gehaltener Sollwert.

        Anders als move_*(): kein Ack-Roundtrip, Bewegung startet sofort. Muss pro
        Frame neu gesendet werden; (0,0,0,0) = Hover/Stop. Nur mock + real.
        """
        self.drone.send_rc_control(lr, fb, ud, yaw)

    def disconnect(self) -> None:
        self.drone.end()

    def tick(self, dt: float | None = None) -> None:
        """Treibt einen Zeitschritt: RC-Sollwert integrieren, in der Sim auch Physik.

        Pro Frame der interaktiven Haupt-Loop aufrufen.
          mock: integriert einen gehaltenen ``send_rc_control``-Sollwert in die Pose.
          sim:  dasselbe, plus ein Stück PyBullet-Physik (nur im cooperative-Mode).
          real: No-Op — die echte Drohne führt RC selbst aus, djitellopy hat kein tick().

        dt: Sekunden seit dem letzten Aufruf. Ohne Angabe aus der monotonen Uhr;
        Tests übergeben ein festes dt für Determinismus.
        """
        # Nur pose-führende Backends (mock/sim) haben tick(); die echte Drohne
        # führt RC selbst aus. Der Protokoll-Check ersetzt den früheren getattr-Hack.
        if isinstance(self.drone, PoseBackend):
            self.drone.tick(dt)

    # ---- nur in der Simulation verfügbar ----
    def position(self) -> tuple[float, float, float, float]:
        if not self.simulated:
            raise RuntimeError("Position wird nur im Simulationsmodus mitgeführt.")
        return cast(PoseBackend, self.drone).pose()

    def report(self) -> None:
        """Protokoll + Karte ausgeben (nur Simulation)."""
        if not self.simulated:
            return
        drone = cast(PoseBackend, self.drone)
        drone.print_log()
        drone.print_map()
