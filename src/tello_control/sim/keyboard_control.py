"""
tello_control.sim.keyboard_control

Drohne per Tastatur durch die PyBullet-Sim fliegen.

Läuft NUR in der conda-Umgebung 'tello-sim'.
Aufruf:  python -m tello_control.sim.keyboard_control     (oder: tello-sim-keys)

Funktionsweise: gehaltene Tasten werden zu einem RC-Geschwindigkeits-Sollwert
(``send_rc_control``, feuern-und-vergessen). Der Sollwert wird in der Logik-Pose
integriert (MockTello.tick) und die Physik folgt ihm beschleunigungsbegrenzt.
Das ist derselbe Pfad wie beim ``--rc``-Gestenmodus — nur die Eingabe ist anders.

Tasten werden aus dem PyBullet-Fenster gelesen, es muss also den Fokus haben.
"""

from __future__ import annotations

import argparse
import time

import pybullet as p

from tello_control.core.controller import DroneController
from tello_control.sim.keyboard_map import (
    CAM_TOGGLE, HELP, HOVER, LAND, QUIT, TAKEOFF, keys_to_velocity,
)

LOOP_HZ = 60


def _pressed_keys(client_id: int) -> tuple[set[str], set[str], bool]:
    """(gehaltene Tasten, neu gedrückte Tasten, Shift gehalten).

    Sondertasten wie B3G_SHIFT (65306) liegen unterhalb von 0x10FFFF und würden
    sonst als exotisches Unicode-Zeichen in `held` landen. Deshalb explizit filtern.
    """
    events = p.getKeyboardEvents(physicsClientId=client_id)
    shift = bool(events.get(p.B3G_SHIFT, 0) & p.KEY_IS_DOWN)

    special = {p.B3G_SHIFT, p.B3G_CONTROL, p.B3G_ALT}
    held: set[str] = set()
    just: set[str] = set()
    for code, state in events.items():
        if code in special or not (0 < code <= 0x10FFFF):
            continue
        char = chr(code).lower()
        if state & p.KEY_IS_DOWN:
            held.add(char)
        if state & p.KEY_WAS_TRIGGERED:
            just.add(char)
    return held, just, shift


def main() -> int:
    ap = argparse.ArgumentParser(description="Tello per Tastatur durch die PyBullet-Sim fliegen.")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Wiedergabegeschwindigkeit (1.0 = Echtzeit)")
    ap.add_argument("--no-follow", action="store_true", help="Kamera folgt der Drohne nicht")
    args = ap.parse_args()

    ctrl = DroneController(
        backend="sim", verbose=True,
        backend_kwargs={"gui": True, "speed": args.speed,
                        "camera_follow": not args.no_follow, "cooperative": True},
    )
    print("Akku:", ctrl.connect(), "%")
    print(HELP)

    client_id = ctrl.drone.client_id
    period = 1.0 / LOOP_HZ
    flying = False
    follow = not args.no_follow

    try:
        while True:
            frame_start = time.monotonic()
            held, just, shift = _pressed_keys(client_id)

            if QUIT in just:
                break

            # Shift = Kameramodus: Nachführung pausiert (Maus-Drag/Zoom gehören dem
            # Nutzer) und die Drohne schwebt, damit sie beim Umsehen nicht wegfliegt.
            ctrl.drone.suspend_camera(shift)

            if CAM_TOGGLE in just:
                follow = not follow
                ctrl.drone.set_camera_follow(follow)
                print("Kamera folgt:", "an" if follow else "aus (fixe Ansicht)")

            if TAKEOFF in just and not flying:
                ctrl.takeoff()
                flying = True
            elif LAND in just and flying:
                ctrl.send_rc_control(0, 0, 0, 0)   # Sollwert nullen, sonst driftet sie
                ctrl.land()
                flying = False

            if flying:
                ctrl.send_rc_control(*((0, 0, 0, 0) if shift else keys_to_velocity(held)))

            ctrl.tick()          # RC -> Logik-Pose -> Physik (immer im Main-Thread)

            if HOVER in just:
                print("Hover")

            slack = period - (time.monotonic() - frame_start)
            if slack > 0:
                time.sleep(slack)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if flying:
                ctrl.send_rc_control(0, 0, 0, 0)
                ctrl.land()
        except Exception as e:                     # Sim evtl. schon zu
            print("Konnte nicht sauber landen:", e)
        ctrl.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
