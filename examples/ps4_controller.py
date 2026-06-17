"""
controller_ps4.py

PS4-Controller: zwei Modi in einer Datei.

  Controller prüfen (zeigt Achsen/Buttons live, keine Drohne nötig):
      python examples/ps4_controller.py --test

  Echte Drohne mit dem Controller fliegen (Tello über WLAN):
      python examples/ps4_controller.py

Steuerung im Flugmodus:
  X/Kreuz       = Start
  Kreis         = Landen
  linker Stick  = Vor/Zurück + Links/Rechts
  rechter Stick = Drehen + Hoch/Runter
  Options       = Beenden
  PS-Button     = EMERGENCY (Motoren sofort aus, nur im Notfall)
"""

import argparse
import time
import pygame

# Controller-Mapping (anpassen, falls dein Controller anders gemappt ist)
AXIS_LEFT_X  = 0     # linker Stick horizontal: strafe links/rechts
AXIS_LEFT_Y  = 1     # linker Stick vertikal: vor/zurück
AXIS_RIGHT_X = 2     # rechter Stick horizontal: drehen/yaw
AXIS_RIGHT_Y = 3     # rechter Stick vertikal: hoch/runter

BTN_TAKEOFF   = 0    # X / Kreuz
BTN_LAND      = 1    # Kreis
BTN_QUIT      = 9    # Options
BTN_EMERGENCY = 10   # PS-Button

DEADZONE  = 0.12
MAX_SPEED = 45       # 20–50 für Indoor sinnvoll


def _init_joystick():
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("Kein Controller gefunden. PS4-Controller per USB/Bluetooth verbinden.")
        raise SystemExit
    js = pygame.joystick.Joystick(0)
    print("Controller:", js.get_name())
    return js


def run_test():
    """Zeigt Achsen und Buttons live an – zum Prüfen des Mappings."""
    js = _init_joystick()
    print("Achsen:", js.get_numaxes(), " Buttons:", js.get_numbuttons())
    print("Bewege Sticks/Buttons. Ctrl-C zum Beenden.\n")
    try:
        while True:
            pygame.event.pump()
            axes = [round(js.get_axis(i), 2) for i in range(js.get_numaxes())]
            buttons = [js.get_button(i) for i in range(js.get_numbuttons())]
            print("Axes:", axes, "Buttons:", buttons, end="\r")
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        pygame.quit()


def _scale_axis(value, invert=False):
    if abs(value) < DEADZONE:
        return 0
    if invert:
        value = -value
    return int(max(-100, min(100, value * MAX_SPEED)))


def _pressed_once(js, button, old_buttons):
    return js.get_button(button) and not old_buttons.get(button, 0)


def run_fly():
    """Fliegt die echte Tello per Controller (send_rc_control)."""
    from djitellopy import Tello   # erst laden, wenn wirklich geflogen wird

    js = _init_joystick()
    tello = Tello()
    print("Verbinde mit Tello ...")
    tello.connect()
    print("Akku:", tello.get_battery(), "%")

    flying = False
    old_buttons = {}
    print(__doc__.split("Steuerung im Flugmodus:")[1])

    try:
        while True:
            pygame.event.pump()

            if _pressed_once(js, BTN_TAKEOFF, old_buttons) and not flying:
                print("\nTakeoff"); tello.takeoff(); flying = True
            if _pressed_once(js, BTN_LAND, old_buttons) and flying:
                print("\nLand"); tello.send_rc_control(0, 0, 0, 0); tello.land(); flying = False
            if _pressed_once(js, BTN_EMERGENCY, old_buttons):
                print("\nEMERGENCY"); tello.emergency(); flying = False; break
            if _pressed_once(js, BTN_QUIT, old_buttons):
                print("\nBeenden"); break

            for b in range(js.get_numbuttons()):
                old_buttons[b] = js.get_button(b)

            # Tello RC: left_right, forward_backward, up_down, yaw
            lr  = _scale_axis(js.get_axis(AXIS_LEFT_X))
            fb  = _scale_axis(js.get_axis(AXIS_LEFT_Y), invert=True)
            ud  = _scale_axis(js.get_axis(AXIS_RIGHT_Y), invert=True)
            yaw = _scale_axis(js.get_axis(AXIS_RIGHT_X))
            if flying:
                tello.send_rc_control(lr, fb, ud, yaw)

            time.sleep(0.05)
    finally:
        print("\nStoppe Steuerung.")
        try:
            tello.send_rc_control(0, 0, 0, 0)
            if flying:
                tello.land()
        except Exception as e:
            print("Konnte nicht sauber landen:", e)
        tello.end()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser(description="PS4-Controller: testen oder Tello fliegen.")
    parser.add_argument("--test", action="store_true",
                        help="Nur Controller prüfen (Achsen/Buttons), keine Drohne")
    args = parser.parse_args()
    if args.test:
        run_test()
    else:
        run_fly()


if __name__ == "__main__":
    main()
