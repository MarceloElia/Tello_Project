"""
demo.py

Demo-Flüge über den DroneController – wählbares Backend.

Modi:
    cube       Würfel in der Luft fliegen
    functions  alle Steuerbefehle der Reihe nach vorführen (mit Ansage + Pause)

Backend (--backend):
    mock   reine Logik, kein WLAN, kein Sim  (Standard, im venv)
    sim    PyBullet-Physik im 3D-Fenster      (conda-Env tello-sim)
    real   echte Tello über WLAN              (im venv)

Beispiele:
    python examples/demo.py cube                      # Würfel im Mock
    python examples/demo.py cube --backend sim        # Würfel im 3D-Fenster
    python examples/demo.py cube --backend real       # Würfel auf echter Drohne
    python examples/demo.py functions                 # alle Funktionen im Mock
    python examples/demo.py cube --side 30            # kleinerer Würfel (Raum eng)
"""

import argparse
import time

from tello_control.core.controller import DroneController


def fly_cube(c, side):
    c.takeoff()
    # untere Fläche
    c.forward(side); c.right(side); c.back(side); c.left(side)
    # senkrechte Kante hoch
    c.up(side)
    # obere Fläche
    c.forward(side); c.right(side); c.back(side); c.left(side)
    # wieder runter
    c.down(side)
    c.land()


def _announce(title, desc, pause):
    print("\n" + "=" * 55)
    print(f"  NÄCHSTE FUNKTION: {title}")
    if desc:
        print(f"  {desc}")
    print("=" * 55)
    for i in range(pause, 0, -1):
        print(f"  → startet in {i}s ...", end="\r")
        time.sleep(1)
    print()


def demo_functions(c, pause):
    is_sim = c.simulated

    _announce("battery()", "Akkustand abfragen", pause)
    print(f"  Akkustand: {c.battery()} %")

    _announce("takeoff()", "Drohne startet, steigt auf ~100 cm", pause)
    c.takeoff()

    _announce("height()", "Aktuelle Höhe abfragen", pause)
    print(f"  Höhe: {c.height()} cm")

    if is_sim:
        _announce("position()", "X / Y / Z / Yaw (nur Simulation)", pause)
        print("  Position:", c.position())

    for name, desc, fn in [
        ("up(30)",        "30 cm steigen",                 lambda: c.up(30)),
        ("down(30)",      "30 cm sinken",                  lambda: c.down(30)),
        ("forward(30)",   "30 cm vorwärts",                lambda: c.forward(30)),
        ("back(30)",      "30 cm zurück",                  lambda: c.back(30)),
        ("right(30)",     "30 cm nach rechts",             lambda: c.right(30)),
        ("left(30)",      "30 cm nach links",              lambda: c.left(30)),
        ("rotate_cw(90)", "90° im Uhrzeigersinn drehen",   lambda: c.rotate_cw(90)),
        ("rotate_ccw(90)","90° gegen Uhrzeigersinn drehen",lambda: c.rotate_ccw(90)),
    ]:
        _announce(name, desc, pause)
        fn()

    _announce("land()", "Drohne landet", pause)
    c.land()


def main():
    parser = argparse.ArgumentParser(description="Demo-Flüge über den DroneController.")
    parser.add_argument("mode", choices=["cube", "functions"], help="Demo-Modus")
    parser.add_argument("--backend", choices=["mock", "sim", "real"], default="mock")
    parser.add_argument("--side", type=int, default=50, help="Würfel-Kantenlänge in cm")
    parser.add_argument("--speed", type=float, default=1.5, help="Sim-Geschwindigkeit")
    parser.add_argument("--pause", type=int, default=2, help="Ansage-Pause (functions)")
    args = parser.parse_args()

    kw = ({"gui": True, "speed": args.speed, "camera_follow": True}
          if args.backend == "sim" else None)
    c = DroneController(backend=args.backend, verbose=True, backend_kwargs=kw)
    print("Akku:", c.connect(), "%\n")

    try:
        if args.mode == "cube":
            fly_cube(c, args.side)
        else:
            demo_functions(c, args.pause)
    finally:
        if c.simulated:
            c.report()
        c.disconnect()


if __name__ == "__main__":
    main()
