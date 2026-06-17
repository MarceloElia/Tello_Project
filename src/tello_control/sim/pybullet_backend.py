"""
pybullet_backend.py

Physik-Backend für den DroneController, auf Basis von gym-pybullet-drones (PyBullet).
Die Mittelstufe zwischen MockTello (reine Logik) und echter Drohne.

Läuft NUR in der conda-Umgebung 'tello-sim' (Python 3.11), nicht im 3.14-venv.

Designidee:
  PyBulletBackend erbt von MockTello und erbt damit die komplette Logik:
  Positionsverfolgung (x/y/z/yaw), Befehlsprotokoll, Karte, SDK-Sicherheitschecks.
  Überschrieben werden nur die Flugmethoden – sie rufen erst super() (analytische
  Pose + Logging + Checks, exakt wie Mock) und treiben dann die echte Physik im
  3D-Fenster zu dieser Pose. So bleibt die Befehlssemantik 1:1 wie beim Mock,
  bekommt aber echte Flugdynamik fürs Auge und für Regelungs-Experimente.

Koordinaten:
  MockTello: x=rechts, y=vorwärts, z=hoch (cm), yaw im Uhrzeigersinn (Grad).
  PyBullet-Welt: +X=rechts, +Y=vorwärts, +Z=hoch (Meter), yaw gegen Uhrzeigersinn (rad).
  → world = (x/100, y/100, z/100),  pyb_yaw = -radians(yaw).
"""

import math
import time
import numpy as np

try:
    import pybullet as p
    from gym_pybullet_drones.envs.CtrlAviary import CtrlAviary
    from gym_pybullet_drones.control.DSLPIDControl import DSLPIDControl
    from gym_pybullet_drones.utils.enums import DroneModel
except ImportError as _e:
    raise ImportError(
        "PyBullet / gym-pybullet-drones not installed. "
        "Run: conda env create -f environment-sim.yml  (conda env tello-sim)"
    ) from _e

from tello_control.core.mock_tello import MockTello

CTRL_FREQ = 240          # Regel-/Physikfrequenz (Hz)
POS_TOL   = 0.03         # m – Zielradius
VEL_TOL   = 0.05         # m/s – als "ruhig" gewertet
MAX_FLY_S = 6.0          # Sekunden Timeout pro Bewegung
GROUND_Z  = 0.05         # m – Starthöhe am Boden


class PyBulletBackend(MockTello):
    def __init__(self, verbose=True, gui=True, speed=2.0, camera_follow=True,
                 cooperative=False):
        """
        speed: Wiedergabe-Geschwindigkeit. 1.0 = Echtzeit, 2.0 = doppelt so schnell,
               <=0 = so schnell wie möglich (kein Bremsen).
        camera_follow: Kamera folgt der Drohne (Zoom/Winkel bleiben deine).
        cooperative: Wenn True, blockieren Flugbefehle NICHT (sie setzen nur die
            Logik-Pose). Die Physik wird stattdessen vom Aufrufer über tick() pro
            Frame im Main-Thread vorangetrieben. Für interaktive Loops (Gesten/
            Sprache), bei denen die Webcam-Anzeige flüssig bleiben muss und PyBullet
            (Metal/OpenGL) zwingend im Main-Thread laufen muss. Scripts (demo_sim,
            demo.py) lassen es auf False → blockierendes Anfliegen wie gehabt.
        """
        super().__init__(verbose=verbose)
        self._gui = gui
        self._speed = speed
        self._camera_follow = camera_follow
        self._cooperative = cooperative
        # Physik-Schritte pro tick() in cooperative-Mode. ~8 Schritte/Frame bei
        # ~30 fps ≈ Echtzeit (CTRL_FREQ=240); mit speed skaliert.
        self._steps_per_tick = max(1, int(round(8 * (speed if speed > 0 else 5))))
        self._env = None
        self._ctrl = None
        self._obs = None

    # ---------- Sim-Aufbau ----------
    def connect(self):
        super().connect()   # setzt connected + loggt
        self._env = CtrlAviary(
            drone_model=DroneModel.CF2X, num_drones=1,
            initial_xyzs=np.array([[0.0, 0.0, GROUND_Z]]),
            pyb_freq=CTRL_FREQ, ctrl_freq=CTRL_FREQ, gui=self._gui,
        )
        self._ctrl = DSLPIDControl(drone_model=DroneModel.CF2X)
        self._obs, _ = self._env.reset()
        self._setup_camera()
        self._say("🎮 PyBullet-Sim bereit (3D-Fenster offen).")

    def _setup_camera(self):
        """Saubere Startansicht: Seitenpanels aus, Schatten an, gute Perspektive."""
        if not self._gui:
            return
        cid = self._env.CLIENT
        p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0, physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1, physicsClientId=cid)
        p.resetDebugVisualizerCamera(
            cameraDistance=2.0, cameraYaw=50, cameraPitch=-30,
            cameraTargetPosition=[0, 0, 1], physicsClientId=cid,
        )

    def _follow_camera(self, pos):
        """Kamera-Ziel auf die Drohne setzen, Zoom/Winkel des Users beibehalten."""
        if not (self._gui and self._camera_follow):
            return
        cid = self._env.CLIENT
        cam = p.getDebugVisualizerCamera(physicsClientId=cid)
        yaw, pitch, dist = cam[8], cam[9], cam[10]
        p.resetDebugVisualizerCamera(dist, yaw, pitch, pos.tolist(), physicsClientId=cid)

    # ---------- Physik-Loop ----------
    def _sim_goto(self, x_cm, y_cm, z_cm, yaw_deg):
        """Fliegt die PyBullet-Drohne zur Zielpose (MockTello-Konvention)."""
        if self._env is None:
            return
        target = np.array([x_cm / 100.0, y_cm / 100.0, z_cm / 100.0])
        target_rpy = np.array([0.0, 0.0, -math.radians(yaw_deg)])
        max_steps = int(MAX_FLY_S * CTRL_FREQ)

        for i in range(max_steps):
            try:
                state = self._obs[0]
                rpm = self._ctrl.computeControlFromState(
                    control_timestep=1.0 / CTRL_FREQ, state=state,
                    target_pos=target, target_rpy=target_rpy,
                )[0]
                o, _, _, _, _ = self._env.step(rpm.reshape(1, 4))
                self._obs = o
            except Exception as e:
                self._say(f"⛔ Physik-Fehler: {e}. Notlandung.")
                super().emergency()
                return

            pos = self._obs[0][0:3]
            if self._gui and self._camera_follow and i % 8 == 0:
                self._follow_camera(pos)
            if self._speed and self._speed > 0:
                time.sleep((1.0 / CTRL_FREQ) / self._speed)

            vel = self._obs[0][10:13]
            if np.linalg.norm(pos - target) < POS_TOL and np.linalg.norm(vel) < VEL_TOL:
                break

    def tick(self):
        """Cooperative-Mode: eine kleine Portion Physik Richtung Logik-Pose.

        MUSS im Main-Thread aufgerufen werden (PyBullet-GUI = Metal/OpenGL).
        Pro Frame der Haupt-Loop aufrufen. Nicht-blockierend: macht nur
        self._steps_per_tick Schritte und kehrt zurück; hält auch im Stillstand
        die Pose (PID-Schwebeflug). Die Logik-Pose (self.x/y/z/yaw) ist Sollwert,
        sie wird von den Flugbefehlen gesetzt – hier nie überschrieben.
        """
        if self._env is None:
            return
        target = np.array([self.x / 100.0, self.y / 100.0,
                           max(self.z / 100.0, GROUND_Z)])
        target_rpy = np.array([0.0, 0.0, -math.radians(self.yaw)])

        for _ in range(self._steps_per_tick):
            state = self._obs[0]
            rpm = self._ctrl.computeControlFromState(
                control_timestep=1.0 / CTRL_FREQ, state=state,
                target_pos=target, target_rpy=target_rpy,
            )[0]
            o, _, _, _, _ = self._env.step(rpm.reshape(1, 4))
            self._obs = o

        if self._gui and self._camera_follow:
            self._follow_camera(self._obs[0][0:3])

    # ---------- Flugmethoden: erst Logik (super), dann Physik ----------
    def takeoff(self):
        super().takeoff()                       # setzt z=100, Checks, Logging
        if not self._cooperative:
            self._sim_goto(self.x, self.y, self.z, self.yaw)

    def land(self):
        super().land()                          # setzt z=0
        if not self._cooperative:
            self._sim_goto(self.x, self.y, GROUND_Z * 100, self.yaw)

    def emergency(self):
        super().emergency()                     # Motoren aus, kein Flug mehr

    def _after_move(self):
        # cooperative: nur Logik-Pose gesetzt (super() im Aufrufer), Physik via tick()
        if not self._cooperative:
            self._sim_goto(self.x, self.y, self.z, self.yaw)

    def end(self):
        if self._env is not None:
            self._env.close()
            self._env = None
        self._ctrl = None
        super().end()


# Generate the 8 movement overrides: each delegates to MockTello's implementation
# (safety checks + pose update + logging) then drives physics to the new pose.
def _make_move_override(method_name: str):
    def _override(self, val):
        getattr(MockTello, method_name)(self, val)
        self._after_move()
    _override.__name__ = method_name
    return _override

for _n in ("move_forward", "move_back", "move_left", "move_right",
           "move_up", "move_down", "rotate_clockwise", "rotate_counter_clockwise"):
    setattr(PyBulletBackend, _n, _make_move_override(_n))
del _n, _make_move_override
