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

from tello_control.core.mock_tello import MockTello


class DroneController:
    """
    Drei Backends:
        backend="mock" → MockTello       (reine Logik, kein WLAN, Standard)
        backend="sim"  → PyBulletBackend (Physik-Sim, 3D-Fenster, conda-Env tello-sim)
        backend="real" → djitellopy.Tello (echte Drohne über WLAN)

    Abwärtskompatibel: simulated=True → "mock", simulated=False → "real".
    """

    def __init__(self, backend=None, simulated=None, verbose=True, backend_kwargs=None):
        # Backend bestimmen (alte simulated-API weiter unterstützen)
        if backend is None:
            backend = "mock" if (simulated is None or simulated) else "real"
        if backend not in ("mock", "sim", "real"):
            raise ValueError(f"Unbekanntes Backend '{backend}'. Erlaubt: mock, sim, real.")

        self.backend = backend
        # mock UND sim führen Position mit → für position()/report() als "simuliert" behandeln
        self.simulated = backend in ("mock", "sim")
        kw = backend_kwargs or {}   # z.B. {"gui": True, "realtime": True} für sim

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
    def connect(self):
        self.drone.connect()
        return self.battery()

    def battery(self):
        return self.drone.get_battery()

    def height(self):
        return self.drone.get_height()

    # ---- Flug ----
    def takeoff(self):
        self.drone.takeoff()

    def land(self):
        self.drone.land()

    def emergency(self):
        self.drone.emergency()

    # ---- Bewegung (klare, kurze Namen für deine Steuerlogik) ----
    def forward(self, cm):  self.drone.move_forward(cm)
    def back(self, cm):     self.drone.move_back(cm)
    def left(self, cm):     self.drone.move_left(cm)
    def right(self, cm):    self.drone.move_right(cm)
    def up(self, cm):       self.drone.move_up(cm)
    def down(self, cm):     self.drone.move_down(cm)
    def rotate_cw(self, deg):  self.drone.rotate_clockwise(deg)
    def rotate_ccw(self, deg): self.drone.rotate_counter_clockwise(deg)

    def send_rc_control(self, lr, fb, ud, yaw):
        """Nicht-blockierende Geschwindigkeitssteuerung (RC). Gehaltener Sollwert.

        Anders als move_*(): kein Ack-Roundtrip, Bewegung startet sofort. Muss pro
        Frame neu gesendet werden; (0,0,0,0) = Hover/Stop. Nur mock + real.
        """
        self.drone.send_rc_control(lr, fb, ud, yaw)

    def disconnect(self):
        self.drone.end()

    def tick(self):
        """Treibt die Physik einen Schritt weiter (nur Sim im cooperative-Mode).

        Pro Frame der interaktiven Haupt-Loop aufrufen. Für mock/real ein No-Op,
        da diese Backends kein tick() haben.
        """
        tick = getattr(self.drone, "tick", None)
        if tick is not None:
            tick()

    # ---- nur in der Simulation verfügbar ----
    def position(self):
        if not self.simulated:
            raise RuntimeError("Position wird nur im Simulationsmodus mitgeführt.")
        return (self.drone.x, self.drone.y, self.drone.z, self.drone.yaw)

    def report(self):
        """Protokoll + Karte ausgeben (nur Simulation)."""
        if not self.simulated:
            return
        self.drone.print_log()
        self.drone.print_map()
