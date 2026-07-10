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

# Farben (Sim ist ein Schauobjekt: die Drohne muss das hellste Ding im Bild sein)
FLOOR_RGBA  = [0.87, 0.83, 0.74, 1.0]    # warmes Beige
GRID_RGB    = [0.62, 0.58, 0.50]         # Raster, dezent dunkler als der Boden
EDGE_RGB    = [0.45, 0.42, 0.36]         # Feldgrenze
BG_RGB      = [0.15, 0.16, 0.19]         # dunkler Hintergrund -> Boden hebt sich ab
DRONE_RGBA  = [1.00, 0.45, 0.08, 1.0]    # kräftiges Orange
DROP_RGB    = [0.20, 0.35, 0.75]         # Lotlinie, gegen Beige gut sichtbar


class PyBulletBackend(MockTello):
    def __init__(self, verbose=True, gui=True, speed=2.0, camera_follow=True,
                 cooperative=False, show_gui_panel=False):
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
        show_gui_panel: PyBullets Seitenpanel einblenden. Nötig, damit die Slider aus
            tuning_panel.py sichtbar sind. Default aus, weil das Panel sonst in der
            Würfel-Demo und den Demo-Videos im Bild hängt.
        """
        super().__init__(verbose=verbose)
        self._gui = gui
        self._show_gui_panel = show_gui_panel
        # Flugparameter als Instanzwerte: zur Laufzeit über set_flight_limits() änderbar.
        self._cruise = CRUISE_MS
        self._max_acc = MAX_ACC
        self._yaw_rate = YAW_RATE
        self._yaw_acc = YAW_ACC
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
        self._camera_suspended = False   # Shift gehalten -> Maus gehört dem Nutzer
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
        self._ramp = VectorRamp(self._obs[0][0:3], self._cruise, self._max_acc)
        self._yaw_ramp = YawRamp(float(self._obs[0][9]), self._yaw_rate, self._yaw_acc)
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

        # Die drei Vorschau-Viewports (RGB / Tiefe / Segmentierung) rendern die Szene
        # JEDEN Frame zusätzlich, per CPU über den Tiny Renderer. Bei COV_ENABLE_GUI=0
        # waren sie nur versteckt, nicht aus — sobald das Panel für die Slider das GUI
        # einschaltet, kosten sie ein Vielfaches der eigentlichen Physik. Explizit aus.
        for preview in (p.COV_ENABLE_RGB_BUFFER_PREVIEW,
                        p.COV_ENABLE_DEPTH_BUFFER_PREVIEW,
                        p.COV_ENABLE_SEGMENTATION_MARK_PREVIEW):
            p.configureDebugVisualizer(preview, 0, physicsClientId=cid)

        # Das Seitenpanel beherbergt die Slider aus tuning_panel.py. Ohne Panel bleiben
        # sie unsichtbar (lesbar wären sie trotzdem).
        p.configureDebugVisualizer(p.COV_ENABLE_GUI, 1 if self._show_gui_panel else 0,
                                   physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_SHADOWS, 1, physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_KEYBOARD_SHORTCUTS, 0, physicsClientId=cid)
        p.configureDebugVisualizer(p.COV_ENABLE_MOUSE_PICKING, 0, physicsClientId=cid)
        # Dunkler, neutraler Hintergrund: die hellgraue Drohne hebt sich klar ab.
        p.configureDebugVisualizer(rgbBackground=BG_RGB, physicsClientId=cid)
        p.configureDebugVisualizer(lightPosition=[3.0, -3.0, 5.0], physicsClientId=cid)
        p.resetDebugVisualizerCamera(
            cameraDistance=3.2, cameraYaw=48, cameraPitch=-22,
            cameraTargetPosition=[0, 0, 1.0], physicsClientId=cid,
        )

    def _color_drone(self):
        """Drohne kräftig einfärben. Die CF2X-URDF ist dunkelgrau und geht vor jedem
        Untergrund unter — im Sim ist sie aber das einzige, worauf man schaut."""
        if not self._gui or self._env is None:
            return
        cid = self._env.CLIENT
        body = int(self._env.DRONE_IDS[0])
        # Basis (-1) und alle Links (Propeller) einfärben.
        for link in range(-1, p.getNumJoints(body, physicsClientId=cid)):
            p.changeVisualShape(body, link, rgbaColor=DRONE_RGBA, physicsClientId=cid)

    def _setup_scene(self):
        """Beiger Boden, dezentes Raster, kräftig orange Drohne.

        Der ursprüngliche helle Betonboden + cremeweiße Drahtwürfel gaben kaum
        Kontrast: die dunkelgraue Crazyflie verschwand, und die 12 Würfelkanten zogen
        den Blick stärker auf sich als die Drohne. Jetzt trägt die Drohne die Farbe,
        der Boden bleibt ruhig, und der Hintergrund ist dunkel, damit sich das
        Spielfeld klar absetzt.

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

        self._color_drone()

        # ── Beiger, matter Boden (überdeckt das Schachbrett) ──────────────────
        floor_vis = p.createVisualShape(
            p.GEOM_BOX, halfExtents=[W, D, 0.005],
            rgbaColor=FLOOR_RGBA,
            physicsClientId=cid,
        )
        p.createMultiBody(
            baseMass=0, baseCollisionShapeIndex=-1,
            baseVisualShapeIndex=floor_vis,
            basePosition=[0, 0, 0.006],
            physicsClientId=cid,
        )

        # ── Bodenraster: Maßstab und Tiefe, ohne vom Objekt abzulenken ────────
        GW, GZ = 1.0, 0.012
        n = int(W / GRID)
        for i in range(-n, n + 1):
            c = i * GRID
            p.addUserDebugLine([c, -D, GZ], [c, D, GZ], GRID_RGB, GW, physicsClientId=cid)
            p.addUserDebugLine([-W, c, GZ], [W, c, GZ], GRID_RGB, GW, physicsClientId=cid)

        # Umrandung dunkler: klare Feldgrenze
        edge = [(-W,-D), (W,-D), (W,D), (-W,D)]
        for i in range(4):
            a, b = edge[i], edge[(i + 1) % 4]
            p.addUserDebugLine([a[0], a[1], GZ], [b[0], b[1], GZ],
                               EDGE_RGB, 2.0, physicsClientId=cid)

        # ── Koordinaten-Achsen (Ursprung) ─────────────────────────────────────
        AZ = 0.02
        p.addUserDebugLine([0,0,AZ], [0.6,0,  AZ],  [1.0,0.25,0.25], 3.0, physicsClientId=cid)
        p.addUserDebugLine([0,0,AZ], [0,  0.6,AZ],  [0.30,0.95,0.40], 3.0, physicsClientId=cid)
        p.addUserDebugText("X", [0.65,0,   AZ],  [1.0,0.25,0.25], 0.9, physicsClientId=cid)
        p.addUserDebugText("Y", [0,   0.65,AZ],  [0.30,0.95,0.40], 0.9, physicsClientId=cid)

        # ── Höhenmast am Ursprung: Höhe direkt an der Drohne ablesbar ─────────
        p.addUserDebugLine([0, 0, AZ], [0, 0, 2.6], [0.22, 0.30, 0.55], 1.5,
                           physicsClientId=cid)
        for h in (0.5, 1.0, 1.5, 2.0, 2.5):
            p.addUserDebugLine([-0.07, 0, h], [0.07, 0, h], [0.20, 0.35, 0.75], 2.0,
                               physicsClientId=cid)
            p.addUserDebugText(f"{h:.1f}", [0.10, 0, h], [0.25, 0.30, 0.40], 0.8,
                               physicsClientId=cid)

        p.configureDebugVisualizer(p.COV_ENABLE_RENDERING, 1, physicsClientId=cid)

    def set_camera_follow(self, enabled: bool) -> None:
        """Kamera-Nachführung dauerhaft an/aus (Taste 'c' in keyboard_control)."""
        self._camera_follow = bool(enabled)

    # ---------- Live-Tuning (tuning_panel.py) ----------
    def set_gui_panel(self, visible: bool) -> None:
        """PyBullets Seitenpanel (und damit die Slider) zur Laufzeit ein-/ausblenden.

        Das Overlay kostet pro Frame spürbar Rechenzeit — auf macOS/Metal genug, um die
        Flugansicht ruckeln zu lassen. Deshalb: Panel nur im Einstellmodus sichtbar,
        beim Fliegen aus. Die Slider-IDs bleiben gültig, sie sind nur unsichtbar.
        """
        self._show_gui_panel = bool(visible)
        if self._gui and self._env is not None:
            p.configureDebugVisualizer(p.COV_ENABLE_GUI, 1 if visible else 0,
                                       physicsClientId=self._env.CLIENT)

    def set_flight_limits(self, cruise=None, max_acc=None, yaw_rate=None, yaw_acc=None):
        """Sollwert-Grenzen zur Laufzeit ändern. yaw_* in rad/s bzw. rad/s²."""
        if cruise is not None:
            self._cruise = float(cruise)
        if max_acc is not None:
            self._max_acc = float(max_acc)
        if yaw_rate is not None:
            self._yaw_rate = float(yaw_rate)
        if yaw_acc is not None:
            self._yaw_acc = float(yaw_acc)
        if self._ramp is not None:
            self._ramp.v_max, self._ramp.a_max = self._cruise, self._max_acc
        if self._yaw_ramp is not None:
            self._yaw_ramp.v_max, self._yaw_ramp.a_max = self._yaw_rate, self._yaw_acc

    def set_pid_gains(self, **arrays):
        """z.B. set_pid_gains(**pid_arrays(...)) — setzt P/I/D_COEFF_FOR auf dem Regler."""
        if self._ctrl is None:
            return
        for name, value in arrays.items():
            setattr(self._ctrl, name, np.asarray(value, dtype=float))

    def reset_pid_state(self):
        """Integrator und Fehlerhistorie leeren.

        DSLPIDControl hält `integral_pos_e`. Wird I live hochgezogen, multipliziert der
        neue Gain einen alten, aufgelaufenen Integralfehler — die Drohne bekommt einen
        Schlag. Nach jeder größeren Gain-Änderung also zurücksetzen.
        """
        if self._ctrl is not None:
            self._ctrl.reset()

    def suspend_camera(self, suspended: bool) -> None:
        """Nachführung kurzzeitig aussetzen (Shift halten), damit die Maus frei ist.

        Solange die Sim jeden Frame `resetDebugVisualizerCamera` ruft, überschreibt sie
        einen laufenden Maus-Drag. Statt das mit einer Totzone zu umgehen (die erzeugt
        genau das ruckartige Nachspringen der Kamera), wird sie hier komplett gestoppt.
        """
        self._camera_suspended = bool(suspended)

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
            DROP_RGB, 1.5, **kwargs,
        )

    def _follow_camera(self, pos):
        """Kamera-Ziel weich der Drohne nachführen, Zoom/Winkel des Users beibehalten.

        Ein hartes Setzen auf die Drohnenposition überträgt jede Regelschwingung 1:1
        aufs Bild — das Ruckeln sitzt dann in der Kamera, nicht in der Drohne.
        Exponentielle Glättung dämpft das.

        JEDEN Frame nachführen, nie mit einer Totzone arbeiten: eine Totzone lässt die
        Kamera in Sprüngen von ihrer Größe nachhaken, und genau das sieht man als
        Ruckeln (bei fixierter Kamera war die Bewegung ja sichtbar flüssig). Damit die
        Maus trotzdem frei bleibt, pausiert `suspend_camera()` die Nachführung
        vollständig, solange Shift gehalten wird.
        """
        self._update_ground_marker(pos)
        if not (self._gui and self._camera_follow) or self._camera_suspended:
            return
        cid = self._env.CLIENT
        self._cam_target += CAM_LERP * (np.asarray(pos, dtype=float) - self._cam_target)

        cam = p.getDebugVisualizerCamera(physicsClientId=cid)
        yaw, pitch, dist = cam[8], cam[9], cam[10]   # Maus-Zoom/-Winkel übernehmen
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
        # Instanzwerte, nicht die Konstanten: die Slider dürfen das Zeitbudget mitziehen.
        budget_s = dist / max(self._cruise, 1e-6) + self._cruise / self._max_acc + 3.0
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
