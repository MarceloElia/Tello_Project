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


def draw_overlay(frame_bgr, gesture, last_cmd, flying, streak, stable, mode):
    h, w = frame_bgr.shape[:2]

    cv2.rectangle(frame_bgr, (0, 0), (w, 70), (30, 30, 30), -1)

    label = GESTURE_LABELS.get(gesture, "?")
    color = GREEN if gesture != Gesture.UNKNOWN else ORANGE
    cv2.putText(frame_bgr, label, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2)

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

    cv2.putText(frame_bgr, "t=takeoff  e=EMERGENCY  q=quit", (w - 260, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

    return frame_bgr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true",
                        help="Echte Drohne statt Mock")
    parser.add_argument("--sim", action="store_true",
                        help="Physik-Sim (PyBullet) statt Mock")
    parser.add_argument("--fpv", action="store_true",
                        help="Drohnenkamera als zweites Fenster anzeigen (nur mit --real)")
    args = parser.parse_args()

    backend = "real" if args.real else ("sim" if args.sim else "mock")
    mode = {"real": "REAL", "sim": "SIM", "mock": "MOCK"}[backend]
    real_mode = backend == "real"
    fpv_mode  = args.fpv and real_mode

    print(f"\n=== Tello Gestensteuerung ({mode}) ===")
    print("Gestenerkennung: Mac-Webcam")
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
    last_cmd  = None

    for result in detector.stream():
        cmd = commander.feed(result.gesture)
        if cmd and cmd != "hover":
            last_cmd = cmd

        # Webcam-Fenster mit Gesten-Overlay
        annotated = detector.annotate(result.frame_rgb, result.landmarks)
        display   = cv2.cvtColor(annotated, cv2.COLOR_RGB2BGR)
        display   = draw_overlay(
            display, result.gesture, last_cmd,
            ctrl.drone.flying if not real_mode else True,
            commander._streak, commander._stable, mode,
        )
        cv2.imshow("Gestensteuerung", display)

        # FPV-Fenster (optional)
        if frame_reader is not None:
            drone_frame = frame_reader.frame
            if drone_frame is not None:
                cv2.imshow("Tello FPV", drone_frame)

        # Sim-Physik im Main-Thread voranschieben (No-Op für mock/real).
        ctrl.tick()

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            print("\n[Main] Beende Session...")
            runner.stop()
            if real_mode and ctrl.drone.is_flying:
                ctrl.land()
            break

        if key == ord("e"):
            print("\n[Main] *** EMERGENCY STOP ***")
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
