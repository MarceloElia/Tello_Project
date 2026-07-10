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

import math

from tello_control.core.controller import DroneController
from tello_control.sim.keyboard_map import (
    CAM_TOGGLE, HELP, HOVER, LAND, QUIT, TAKEOFF, keys_to_velocity,
)
from tello_control.sim.tuning_panel import TuningPanel, pid_arrays

LOOP_HZ = 60


ESC = 27                     # PyBullet hat kein B3G_ESCAPE; ESC kommt als roher Code 27.
SETTINGS_KEY = "m"           # garantierter Fallback, falls ESC nicht durchkommt
FLY_KEYS = (65309, 13, 10)   # B3G_RETURN und die beiden Enter-Varianten

_MODE_HELP = """
  ── EINSTELLUNGEN ──  Physik pausiert, Regler links im Fenster.
     ENTER   losfliegen (Panel verschwindet, Ansicht wird flüssig)
     ESC / m zurück hierher
     Buttons: Zurueck zum Menue · PID-Zustand · Defaults
"""


def _pressed_keys(client_id: int) -> tuple[set[str], set[str], bool, set[int]]:
    """(gehaltene Tasten, neu gedrückte Tasten, Shift gehalten, neu gedrückte Rohcodes).

    Sondertasten wie B3G_SHIFT (65306) und B3G_RETURN (65309) liegen unterhalb von
    0x10FFFF und würden sonst als exotisches Unicode-Zeichen in `held` landen.
    Deshalb explizit filtern und die Rohcodes separat zurückgeben.
    """
    events = p.getKeyboardEvents(physicsClientId=client_id)
    shift = bool(events.get(p.B3G_SHIFT, 0) & p.KEY_IS_DOWN)

    special = {p.B3G_SHIFT, p.B3G_CONTROL, p.B3G_ALT, *FLY_KEYS}
    held: set[str] = set()
    just: set[str] = set()
    just_codes: set[int] = set()
    for code, state in events.items():
        if state & p.KEY_WAS_TRIGGERED:
            just_codes.add(code)
        if code in special or not (32 <= code <= 0x10FFFF):
            continue                       # <32 sind Steuerzeichen (ESC = 27)
        char = chr(code).lower()
        if state & p.KEY_IS_DOWN:
            held.add(char)
        if state & p.KEY_WAS_TRIGGERED:
            just.add(char)
    return held, just, shift, just_codes


def main() -> int:
    ap = argparse.ArgumentParser(description="Tello per Tastatur durch die PyBullet-Sim fliegen.")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Wiedergabegeschwindigkeit (1.0 = Echtzeit)")
    ap.add_argument("--no-follow", action="store_true", help="Kamera folgt der Drohne nicht")
    args = ap.parse_args()

    ctrl = DroneController(
        backend="sim", verbose=True,
        backend_kwargs={"gui": True, "speed": args.speed,
                        "camera_follow": not args.no_follow, "cooperative": True,
                        "show_gui_panel": True},
    )
    print("Akku:", ctrl.connect(), "%")
    print(HELP)
    print("  Regler-Panel links im Fenster: Speed/Beschleunigung und PID-Gains live.\n")

    drone = ctrl.drone
    client_id = drone.client_id
    panel = TuningPanel(client_id)
    period = 1.0 / LOOP_HZ
    flying = False
    follow = not args.no_follow
    back_to_menu = False
    frame = 0
    v = panel.read()          # Startwerte = Defaults

    # Zwei Modi in einem Prozess. PyBullets Seitenpanel kostet pro Frame so viel, dass
    # die Flugansicht damit nicht flüssig wird. Also: Panel nur zum Einstellen sichtbar,
    # und dort steht die Physik still — im Einstellmodus ist Bildrate schlicht egal.
    settings_mode = True
    drone.set_gui_panel(True)
    print(_MODE_HELP)

    try:
        while True:
            frame_start = time.monotonic()
            held, just, shift, codes = _pressed_keys(client_id)

            if QUIT in just:
                break

            # ---------- Moduswechsel ----------
            if settings_mode and (codes & set(FLY_KEYS)):
                settings_mode = False
                drone.set_gui_panel(False)          # Overlay weg -> flüssig
                print("Flugmodus. ESC oder 'm' -> zurück zu den Einstellungen.")
            elif not settings_mode and (ESC in codes or SETTINGS_KEY in just):
                settings_mode = True
                if flying:
                    ctrl.send_rc_control(0, 0, 0, 0)   # nicht wegdriften
                drone.set_gui_panel(True)
                print(_MODE_HELP)

            # ---------- Einstellmodus: Slider lesen, Physik pausiert ----------
            if settings_mode:
                if panel.clicked("menu"):
                    back_to_menu = True
                    break
                if panel.clicked("defaults"):
                    panel.reset_to_defaults()      # legt Slider+Buttons neu an
                    drone.reset_pid_state()
                    print("Defaults wiederhergestellt")
                if panel.clicked("reset_pid"):
                    drone.reset_pid_state()
                    print("PID-Zustand zurückgesetzt")

                new_v = panel.read()
                if new_v != v:                     # nur bei echter Änderung anwenden
                    v = new_v
                    drone.set_flight_limits(
                        cruise=v["cruise_ms"], max_acc=v["max_acc"],
                        yaw_rate=math.radians(v["yaw_rate"]),
                        yaw_acc=math.radians(v["yaw_acc"]),
                    )
                    drone.set_pid_gains(**pid_arrays(v["p_xy"], v["p_z"], v["i_xy"],
                                                     v["d_xy"], v["d_z"]))

                # Kein tick(): die Physik ruht, die Drohne bleibt stehen wo sie ist.
                # Deshalb ist das teure Panel hier ohne Folgen.
                time.sleep(period)
                continue

            # ---------- Flugmodus: kein Panel, keine Slider-Abfragen ----------
            frame += 1

            # Shift = Kameramodus: Nachführung pausiert (Maus-Drag/Zoom gehören dem
            # Nutzer) und die Drohne schwebt, damit sie beim Umsehen nicht wegfliegt.
            drone.suspend_camera(shift)

            if CAM_TOGGLE in just:
                follow = not follow
                drone.set_camera_follow(follow)
                print("Kamera folgt:", "an" if follow else "aus (fixe Ansicht)")

            if TAKEOFF in just and not flying:
                ctrl.takeoff()
                flying = True
            elif LAND in just and flying:
                ctrl.send_rc_control(0, 0, 0, 0)   # Sollwert nullen, sonst driftet sie
                ctrl.land()
                flying = False

            if flying:
                rc = (0, 0, 0, 0) if shift else keys_to_velocity(held, int(v["rc_cruise"]))
                ctrl.send_rc_control(*rc)

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

    if back_to_menu:
        print("Zurück zum Menü.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
