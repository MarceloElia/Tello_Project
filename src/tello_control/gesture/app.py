"""
tello_control.gesture.app

Haupt-Loop der Gestensteuerung.

Simulation (Mock):
    python -m tello_control.gesture.app

Echte Drohne:
    python -m tello_control.gesture.app --real

Echte Drohne + FPV-Fenster der Drohnenkamera:
    python -m tello_control.gesture.app --real --fpv

Gestenerkennung läuft immer über die Mac-Webcam.
Tasten: t=takeoff  e=EMERGENCY STOP  q=beenden
"""

import argparse

import cv2
from tello_control.core.controller import DroneController
from tello_control.gesture.detector import GestureDetector, Gesture
from tello_control.gesture.command_map import GestureToCommand
from tello_control.gesture.velocity_map import gesture_to_velocity, VelocityBlender
from tello_control.gesture.runner import AsyncCommandRunner, ThreadedCtrlAdapter

GESTURE_LABELS = {
    Gesture.FIST:          "FAUST              → hover",
    Gesture.THUMBS_UP:     "DAUMEN HOCH        → up 30",
    Gesture.THUMBS_DOWN:   "DAUMEN RUNTER      → down 30",
    Gesture.POINT_FORWARD: "ZEIGEFINGER HOCH   → forward 30",
    Gesture.POINT_LEFT:    "ZEIGEFINGER LINKS  → left 30",
    Gesture.POINT_RIGHT:   "ZEIGEFINGER RECHTS → right 30",
    Gesture.PEACE:         "PEACE              → back 30",
    Gesture.OPEN_HAND:     "OFFENE HAND        → land",
    Gesture.UNKNOWN:       "–",
}

GREEN  = (0, 200, 0)
ORANGE = (0, 165, 255)
WHITE  = (255, 255, 255)
RED    = (0, 0, 220)

_BTN_M  = 8    # margin
_BTN_H  = 54   # button height (fits inside 70 px header)


def btn_rects(w):
    """Return (takeoff_rect, quit_rect) as (x1, y1, x2, y2)."""
    qx1 = w - _BTN_M - 72
    tx1 = qx1 - _BTN_M - 100
    y1, y2 = _BTN_M, _BTN_M + _BTN_H
    return (tx1, y1, tx1 + 100, y2), (qx1, y1, qx1 + 72, y2)


def _draw_btn(frame, rect, label, bg, fg=(255, 255, 255)):
    x1, y1, x2, y2 = rect
    cv2.rectangle(frame, (x1, y1), (x2, y2), bg, -1)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (200, 200, 200), 1)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
    cv2.putText(frame, label,
                (x1 + (x2 - x1 - tw) // 2, y1 + (y2 - y1 + th) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, fg, 2)


def draw_overlay(frame_bgr, gesture, last_cmd, flying, streak, stable, mode,
                 rc_vel=None):
    h, w = frame_bgr.shape[:2]

    cv2.rectangle(frame_bgr, (0, 0), (w, 70), (30, 30, 30), -1)

    label = GESTURE_LABELS.get(gesture, "?")
    color = GREEN if gesture != Gesture.UNKNOWN else ORANGE
    cv2.putText(frame_bgr, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

    if rc_vel is not None:
        # RC-Modus: Geschwindigkeits-Sollwert statt Debounce-Balken anzeigen.
        lr, fb, ud, yaw = rc_vel
        cv2.putText(frame_bgr, f"RC  lr={lr:+d} fb={fb:+d} ud={ud:+d} yaw={yaw:+d}",
                    (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    GREEN if any(rc_vel) else WHITE, 2)
    else:
        bar_w = int((min(streak, stable) / stable) * (w - 20))
        cv2.rectangle(frame_bgr, (10, 42), (10 + bar_w, 58), GREEN, -1)
        cv2.rectangle(frame_bgr, (10, 42), (w - 10, 58), WHITE, 1)

    status = f"[{mode}] Drohne: {'IN DER LUFT' if flying else 'AM BODEN'}"
    if last_cmd:
        status += f"   Letzter Befehl: {last_cmd}"
    cv2.rectangle(frame_bgr, (0, h - 30), (w, h), (30, 30, 30), -1)
    cv2.putText(frame_bgr, status, (10, h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                RED if mode == "REAL" else WHITE, 1)
    cv2.putText(frame_bgr, "e=EMERGENCY", (10, h - 10 - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 80, 80), 1)

    t_rect, q_rect = btn_rects(w)
    _draw_btn(frame_bgr, t_rect, "TAKEOFF", (30, 140, 30))
    _draw_btn(frame_bgr, q_rect, "QUIT",    (80, 80, 80))

    return frame_bgr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true",
                        help="Echte Drohne statt Mock")
    parser.add_argument("--sim", action="store_true",
                        help="Physik-Sim (PyBullet) statt Mock")
    parser.add_argument("--fpv", action="store_true",
                        help="Drohnenkamera als zweites Fenster anzeigen (nur mit --real)")
    parser.add_argument("--rc", action="store_true",
                        help="Kontinuierliche RC-Geschwindigkeitssteuerung statt diskreter Befehle")
    args = parser.parse_args()

    backend = "real" if args.real else ("sim" if args.sim else "mock")
    if args.rc and backend == "sim":
        parser.error("--rc wird mit --sim noch nicht unterstützt (nur mock + real).")
    mode = {"real": "REAL", "sim": "SIM", "mock": "MOCK"}[backend]
    real_mode = backend == "real"
    fpv_mode  = args.fpv and real_mode

    print(f"\n=== Tello Gestensteuerung ({mode}){' · RC' if args.rc else ''} ===")
    print("Gestenerkennung: Mac-Webcam")
    if args.rc:
        print("Modus: kontinuierliche RC-Geschwindigkeit (Geste halten = weiterfliegen)")
    if fpv_mode:
        print("FPV: Drohnenkamera wird als zweites Fenster gezeigt")
    if real_mode:
        print("ACHTUNG: Echte Drohne aktiv. 'e' = Emergency Stop.\n")
    else:
        print("'t' = Takeoff, 'q' = Beenden\n")

    # Im Sim das 3D-Fenster zügig laufen lassen (Gesten kommen schnell).
    # cooperative=True: Flugbefehle blockieren nicht, die Physik wird pro Frame
    # über ctrl.tick() im Main-Thread getrieben (PyBullet muss im Main-Thread sein).
    kw = ({"gui": True, "speed": 2.0, "camera_follow": True, "cooperative": True}
          if backend == "sim" else None)
    ctrl = DroneController(backend=backend, verbose=True, backend_kwargs=kw)
    ctrl.connect()

    # Drohnenkamera nur wenn --fpv
    frame_reader = None
    if fpv_mode:
        ctrl.drone.streamon()
        frame_reader = ctrl.drone.get_frame_read()
        print("Drohnenkamera gestartet.")

    # Flugbefehle laufen im Worker-Thread, damit Webcam + Anzeige flüssig bleiben.
    runner = AsyncCommandRunner(ctrl, verbose=True)

    # Gestenerkennung immer über Mac-Webcam
    detector  = GestureDetector(camera_index=0)
    commander = GestureToCommand(ThreadedCtrlAdapter(runner), verbose=True)
    blender   = VelocityBlender() if args.rc else None   # RC-Modus: geglättete Geschwindigkeit
    last_cmd  = None
    clicked   = []   # mouse-click actions queued from callback

    def on_mouse(event, x, y, _flags, _param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        shape = getattr(on_mouse, "_shape", None)
        if shape is None:
            return
        h, w = shape
        t_rect, q_rect = btn_rects(w)
        if t_rect[0] <= x <= t_rect[2] and t_rect[1] <= y <= t_rect[3]:
            clicked.append("takeoff")
        elif q_rect[0] <= x <= q_rect[2] and q_rect[1] <= y <= q_rect[3]:
            clicked.append("quit")

    rc_vel = None
    for result in detector.stream():
        if blender is not None:
            # RC-Modus: gehaltene Geste → geglätteter Geschwindigkeits-Sollwert,
            # jeden Frame direkt (nicht-blockierend) gesendet. OPEN_HAND = Landen.
            if result.gesture == Gesture.OPEN_HAND:
                rc_vel = blender.update((0, 0, 0, 0))
                if ctrl.drone.is_flying:
                    ctrl.send_rc_control(0, 0, 0, 0)
                    runner.submit("land")
                    last_cmd = "land"
            else:
                target = gesture_to_velocity(result.gesture)
                rc_vel = blender.update(target)
                if ctrl.drone.is_flying:
                    ctrl.send_rc_control(*rc_vel)
                if any(rc_vel):
                    last_cmd = f"rc {rc_vel}"
        else:
            cmd = commander.feed(result.gesture)
            if cmd and cmd != "hover":
                last_cmd = cmd

        # Webcam-Fenster mit Gesten-Overlay
        annotated = detector.annotate(result.frame_rgb, result.landmarks)
        display   = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
        display   = draw_overlay(
            display, result.gesture, last_cmd,
            ctrl.drone.is_flying,
            commander._streak, commander._stable, mode,
            rc_vel=rc_vel,
        )
        cv2.imshow("Gestensteuerung", display)
        on_mouse._shape = display.shape[:2]
        cv2.setMouseCallback("Gestensteuerung", on_mouse)

        # FPV-Fenster (optional)
        if frame_reader is not None:
            drone_frame = frame_reader.frame
            if drone_frame is not None:
                cv2.imshow("Tello FPV", drone_frame)

        # Sim-Physik im Main-Thread voranschieben (No-Op für mock/real).
        ctrl.tick()

        key = cv2.waitKey(1) & 0xFF

        # mouse-button clicks
        while clicked:
            action = clicked.pop(0)
            if action == "quit":
                key = ord("q")
            elif action == "takeoff":
                key = ord("t")

        if key == ord("q"):
            print("\n[Main] Beende Session...")
            if blender is not None and ctrl.drone.is_flying:
                ctrl.send_rc_control(0, 0, 0, 0)   # RC-Sollwert stoppen, sonst driftet sie
            runner.stop()
            if real_mode and ctrl.drone.is_flying:
                ctrl.land()
            break

        if key == ord("e"):
            print("\n[Main] *** EMERGENCY STOP ***")
            if blender is not None and ctrl.drone.is_flying:
                ctrl.send_rc_control(0, 0, 0, 0)   # Sollwert nullen, dann Motoren aus
            ctrl.emergency()        # synchron, sofort – nicht über die Queue
            runner.stop()
            break

        if key == ord("t"):
            # Über den Worker einreihen, damit die Anzeige nicht einfriert.
            runner.submit("takeoff")
            runner.submit("up", 50)
            print("[Main] Takeoff → 150 cm (eingereiht).")

    runner.stop()
    detector.close()
    if frame_reader is not None:
        ctrl.drone.streamoff()
    cv2.destroyAllWindows()

    print("\n=== Session beendet ===")
    if backend in ("mock", "sim"):
        ctrl.report()
    ctrl.disconnect()


if __name__ == "__main__":
    main()
