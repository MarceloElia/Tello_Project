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
from tello_control.sim.motion_profile import VectorRamp, YawRamp

CTRL_FREQ = 240          # Regel-/Physikfrequenz (Hz)
POS_TOL   = 0.03         # m – Zielradius
VEL_TOL   = 0.05         # m/s – als "ruhig" gewertet
MAX_FLY_S = 6.0          # Sekunden Timeout pro Bewegung
GROUND_Z  = 0.05         # m – Starthöhe am Boden
CRUISE_MS = 0.6          # m/s – max. Sollwert-Geschwindigkeit (Anti-Überschwingen)
YAW_RATE  = math.radians(90)   # rad/s – max. Soll-Drehrate
MAX_ACC   = 1.2                # m/s² – Sollwert-Beschleunigung (0 -> CRUISE_MS in 0.5 s)
YAW_ACC   = math.radians(240)  # rad/s² – Soll-Drehbeschleunigung
RENDER_HZ = 60           # Sichtbare Bilder/s; darunter laufen mehrere Physikschritte
CAM_LERP  = 0.12         # Kamera-Nachführung pro Frame (1.0 = hart springen)
CAM_MIN_MOVE = 0.02      # m – darunter Kamera nicht anfassen (sonst stirbt der Maus-Drag)


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
            (Metal/OpenGL) zwingend im Main-Thread laufen muss. Scripts (demo.py)
            lassen es auf False → blockierendes Anfliegen wie gehabt.
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
        # Beschleunigungsbegrenzte Führung des Sollwerts. Ohne sie sieht der PID
        # Stufeneingänge (30-cm-Sprung) bzw. Geschwindigkeitssprünge -> Ruckeln.
        self._ramp = None
        self._yaw_ramp = None
        self._cam_target = None
        self._drop_line = None   # Debug-Item-ID der Lotlinie (wird ersetzt, nicht neu erzeugt)

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
        self._ramp = VectorRamp(self._obs[0][0:3], CRUISE_MS, MAX_ACC)
        self._yaw_ramp = YawRamp(float(self._obs[0][9]), YAW_RATE, YAW_ACC)
        self._cam_target = np.array(self._obs[0][0:3], dtype=float)
        self._setup_camera()
        self._setup_scene()
        self._say("🎮 PyBullet-Sim bereit (3D-Fenster offen).")

    def _setup_camera(self):
        """Saubere Startansicht: Seitenpanels aus, Schatten an, gute Perspektive.

        WICHTIG — COV_ENABLE_KEYBOARD_SHORTCUTS aus: PyBullets GUI belegt Tasten für
        eigene Render-Umschalter (w=Wireframe, s=Schatten, a=AABB, d=Deaktivierung,
        l=Constraint-Limits). Die kollidieren direkt mit der WASD-Flugsteuerung —
        Vorwärtsfliegen schaltete sonst nebenbei das Drahtgitter um.
        Mouse-Picking aus, damit ein Klick nicht die Drohne durch die Luft zerrt.
        """
        if not self._gui:
            return
        cid = self._env.CLIENT
        p.configureDebugVisualizer(p.COV_ENABLE_GUI, 0, physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1, physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_KEYBOARD_SHORTCUTS, 0, physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_MOUSE_PICKING, 0, physicsClientId=cid)
        # Dunkler, neutraler Hintergrund: die hellgraue Drohne hebt sich klar ab.
        p.configureDebugVisualizer(rgbBackground=[0.09, 0.10, 0.13], physicsClientId=cid)
        p.configureDebugVisualizer(lightPosition=[3.0, -3.0, 5.0], physicsClientId=cid)
        p.resetDebugVisualizerCamera(
            cameraDistance=3.2, cameraYaw=48, cameraPitch=-22,
            cameraTargetPosition=[0, 0, 1.0], physicsClientId=cid,
        )

    def _setup_scene(self):
        """Dunkles Studio mit hellem Bodenraster.

        Der frühere helle Betonboden + cremeweiße Drahtwürfel gaben kaum Kontrast:
        die hellgraue Crazyflie verschwand vor hellem Grund, und die 12 Würfelkanten
        zogen den Blick stärker auf sich als die Drohne. Jetzt: dunkler Boden, helles
        Raster als Tiefen-/Entfernungsraster, ein Höhenmast statt Wandmarken.

        Alles rein visuell – kein Collision Shape, keine Physik-Auswirkung.
        """
        if not self._gui:
            return
        cid = self._env.CLIENT

        # Jede addUserDebugLine löst sonst ein Neuzeichnen aus: ~40 Zeichenbefehle
        # ergeben 40 Vollbilder beim Start. Rendering solange stumm schalten.
        p.configureDebugVisualizer(p.COV_ENABLE_RENDERING, 0, physicsClientId=cid)

        W, D = 2.0, 2.0          # halbe Breite/Tiefe des Flugfelds
        GRID = 0.5               # Rasterweite (m)

        # ── Dunkler, matter Boden (überdeckt das Schachbrett) ─────────────────
        floor_vis = p.createVisualShape(
            p.GEOM_BOX, halfExtents=[W, D, 0.005],
            rgbaColor=[0.16, 0.17, 0.20, 1.0],
            physicsClientId=cid,
        )
        p.createMultiBody(
            baseMass=0, baseCollisionShapeIndex=-1,
            baseVisualShapeIndex=floor_vis,
            basePosition=[0, 0, 0.006],
            physicsClientId=cid,
        )

        # ── Bodenraster: Maßstab und Tiefe, ohne vom Objekt abzulenken ────────
        GC, GW, GZ = [0.34, 0.37, 0.42], 1.0, 0.012
        n = int(W / GRID)
        for i in range(-n, n + 1):
            c = i * GRID
            p.addUserDebugLine([c, -D, GZ], [c, D, GZ], GC, GW, physicsClientId=cid)
            p.addUserDebugLine([-W, c, GZ], [W, c, GZ], GC, GW, physicsClientId=cid)

        # Umrandung etwas heller: klare Feldgrenze
        edge = [(-W,-D), (W,-D), (W,D), (-W,D)]
        for i in range(4):
            a, b = edge[i], edge[(i + 1) % 4]
            p.addUserDebugLine([a[0], a[1], GZ], [b[0], b[1], GZ],
                               [0.55, 0.58, 0.64], 2.0, physicsClientId=cid)

        # ── Koordinaten-Achsen (Ursprung) ─────────────────────────────────────
        AZ = 0.02
        p.addUserDebugLine([0,0,AZ], [0.6,0,  AZ],  [1.0,0.25,0.25], 3.0, physicsClientId=cid)
        p.addUserDebugLine([0,0,AZ], [0,  0.6,AZ],  [0.30,0.95,0.40], 3.0, physicsClientId=cid)
        p.addUserDebugText("X", [0.65,0,   AZ],  [1.0,0.25,0.25], 0.9, physicsClientId=cid)
        p.addUserDebugText("Y", [0,   0.65,AZ],  [0.30,0.95,0.40], 0.9, physicsClientId=cid)

        # ── Höhenmast am Ursprung: Höhe direkt an der Drohne ablesbar ─────────
        p.addUserDebugLine([0, 0, AZ], [0, 0, 2.6], [0.35, 0.60, 0.95], 1.5,
                           physicsClientId=cid)
        for h in (0.5, 1.0, 1.5, 2.0, 2.5):
            p.addUserDebugLine([-0.07, 0, h], [0.07, 0, h], [0.55, 0.75, 1.0], 2.0,
                               physicsClientId=cid)
            p.addUserDebugText(f"{h:.1f}", [0.10, 0, h], [0.62, 0.72, 0.85], 0.8,
                               physicsClientId=cid)

        p.configureDebugVisualizer(p.COV_ENABLE_RENDERING, 1, physicsClientId=cid)

    def set_camera_follow(self, enabled: bool) -> None:
        """Kamera-Nachführung zur Laufzeit an/aus (Taste 'c' in keyboard_control)."""
        self._camera_follow = bool(enabled)

    def _update_ground_marker(self, pos):
        """Lotlinie Drohne→Boden. Ohne sie ist die Höhe im 3D-Bild kaum schätzbar."""
        if not self._gui:
            return
        cid = self._env.CLIENT
        kwargs = {"physicsClientId": cid}
        if self._drop_line is not None:
            kwargs["replaceItemUniqueId"] = self._drop_line
        self._drop_line = p.addUserDebugLine(
            [float(pos[0]), float(pos[1]), 0.012],
            [float(pos[0]), float(pos[1]), float(pos[2])],
            [0.95, 0.75, 0.25], 1.5, **kwargs,
        )

    def _follow_camera(self, pos):
        """Kamera-Ziel weich der Drohne nachführen, Zoom/Winkel des Users beibehalten.

        Zwei Fallen, die hier umgangen werden:

        1. Ein hartes Setzen auf die Drohnenposition überträgt jede Regelschwingung
           1:1 aufs Bild — das Ruckeln sitzt dann in der Kamera, nicht in der Drohne.
           Exponentielle Glättung dämpft das.
        2. `resetDebugVisualizerCamera` bei JEDEM Frame killt das Maus-Ziehen: der
           laufende Drag wird von unseren zurückgeschriebenen Werten überschrieben,
           die Ansicht schnappt zurück. Deshalb nur nachführen, wenn sich das
           geglättete Ziel spürbar bewegt hat. Im Schwebeflug fasst die Sim die
           Kamera gar nicht an -> Maus gehört komplett dem Nutzer.
        """
        self._update_ground_marker(pos)
        if not (self._gui and self._camera_follow):
            return
        cid = self._env.CLIENT
        self._cam_target += CAM_LERP * (np.asarray(pos, dtype=float) - self._cam_target)

        cam = p.getDebugVisualizerCamera(physicsClientId=cid)
        current_target = np.asarray(cam[11], dtype=float)
        if np.linalg.norm(self._cam_target - current_target) < CAM_MIN_MOVE:
            return                                   # Maus nicht stören
        yaw, pitch, dist = cam[8], cam[9], cam[10]
        p.resetDebugVisualizerCamera(dist, yaw, pitch, self._cam_target.tolist(),
                                     physicsClientId=cid)

    # ---------- Physik-Loop ----------
    def _step_physics(self, setpoint, yaw_sp, dt):
        """Ein Regel-/Physikschritt auf den gegebenen Sollwert. True = ok."""
        try:
            rpm = self._ctrl.computeControlFromState(
                control_timestep=dt, state=self._obs[0],
                target_pos=setpoint, target_rpy=np.array([0.0, 0.0, yaw_sp]),
            )[0]
            self._obs, _, _, _, _ = self._env.step(rpm.reshape(1, 4))
            return True
        except Exception as e:
            self._say(f"⛔ Physik-Fehler: {e}. Notlandung.")
            super().emergency()
            return False

    def _sim_goto(self, x_cm, y_cm, z_cm, yaw_deg):
        """Fliegt die PyBullet-Drohne zur Zielpose (MockTello-Konvention).

        Der Sollwert wird beschleunigungs- UND geschwindigkeitsbegrenzt ans Ziel
        geführt (trapezförmiges Profil, siehe motion_profile.py). Früher lief er mit
        konstanter Geschwindigkeit los und schnappte am Ende aufs Ziel — zwei
        Geschwindigkeitssprünge, die der PID als Ruck ausbügeln musste.

        Gerendert/geschlafen wird nur alle RENDER_HZ, nicht pro Physikschritt:
        240 sleep()-Aufrufe pro Sekunde sind auf macOS spürbar unregelmäßig.
        """
        if self._env is None:
            return
        final = np.array([x_cm / 100.0, y_cm / 100.0, z_cm / 100.0])
        final_yaw = -math.radians(yaw_deg)
        dt = 1.0 / CTRL_FREQ
        substeps = max(1, CTRL_FREQ // RENDER_HZ)

        dist = float(np.linalg.norm(final - self._ramp.pos))
        # Anfahrt (inkl. Beschleunigen/Bremsen) + Einschwingen, mit Sicherheits-Cap.
        budget_s = dist / max(CRUISE_MS, 1e-6) + CRUISE_MS / MAX_ACC + 3.0
        max_steps = int(min(MAX_FLY_S * 4, budget_s) * CTRL_FREQ)

        for i in range(max_steps):
            setpoint = self._ramp.advance(final, dt)
            yaw_sp = self._yaw_ramp.advance(final_yaw, dt)
            if not self._step_physics(setpoint, yaw_sp, dt):
                return

            if i % substeps == 0:
                if self._gui:
                    self._follow_camera(self._obs[0][0:3])
                if self._speed and self._speed > 0:
                    time.sleep(substeps * dt / self._speed)

            pos, vel = self._obs[0][0:3], self._obs[0][10:13]
            setpoint_settled = (np.linalg.norm(final - self._ramp.pos) < 1e-6
                                and self._ramp.speed == 0.0)
            if (setpoint_settled and np.linalg.norm(pos - final) < POS_TOL
                    and np.linalg.norm(vel) < VEL_TOL):
                break

    def tick(self, dt=None):
        """Cooperative-Mode: eine kleine Portion Physik Richtung Logik-Pose.

        MUSS im Main-Thread aufgerufen werden (PyBullet-GUI = Metal/OpenGL).
        Pro Frame der Haupt-Loop aufrufen. Nicht-blockierend: macht nur
        self._steps_per_tick Schritte und kehrt zurück; hält auch im Stillstand
        die Pose (PID-Schwebeflug).

        Zwei Dinge passieren hier:

        1. ``super().tick(dt)`` integriert einen gehaltenen RC-Sollwert
           (``send_rc_control``) in die Logik-Pose — exakt wie beim MockTello.
           Ohne diesen Aufruf ignorierte die Sim RC-Befehle vollständig; genau
           deshalb war ``--rc --sim`` gesperrt. Bei RC = (0,0,0,0) ein No-Op.
        2. Der Physik-Sollwert wird beschleunigungsbegrenzt an die Logik-Pose
           herangeführt, statt auf sie zu springen. Ein ``move_forward(30)`` war
           vorher ein 30-cm-Stufeneingang für den PID — die härteste denkbare
           Anregung und die Hauptquelle des Ruckelns im interaktiven Modus.
        """
        if self._env is None:
            return

        super().tick(dt)   # RC -> Logik-Pose (No-Op solange kein RC gesetzt ist)

        target = np.array([self.x / 100.0, self.y / 100.0,
                           max(self.z / 100.0, GROUND_Z)])
        target_yaw = -math.radians(self.yaw)
        step_dt = 1.0 / CTRL_FREQ

        for _ in range(self._steps_per_tick):
            setpoint = self._ramp.advance(target, step_dt)
            yaw_sp = self._yaw_ramp.advance(target_yaw, step_dt)
            if not self._step_physics(setpoint, yaw_sp, step_dt):
                return

        if self._gui:
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

    @property
    def client_id(self):
        """PyBullet-Client-ID, z.B. für p.getKeyboardEvents(). None wenn geschlossen."""
        return None if self._env is None else self._env.CLIENT

    def end(self):
        if self._env is not None:
            self._env.close()
            self._env = None
        self._ctrl = None
        self._ramp = self._yaw_ramp = self._cam_target = self._drop_line = None
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
