"""
tello_control.sim.demo

Würfel-Flug in der Physik-Simulation (PyBullet), mit 3D-Fenster.
Echte Quadrotor-Physik im sichtbaren Fenster statt reiner Logik.
(Identisch zu: python examples/demo.py cube --backend sim)

Starten (in der conda-Env tello-sim, aus dem Projektordner):
    conda activate tello-sim
    python -m tello_control.sim.demo

Am Ende: Befehlsprotokoll + Flugbahn von oben.
"""

from tello_control.core.controller import DroneController

SIDE = 50   # Kantenlänge in cm


def fly_cube(c):
    c.takeoff()

    # untere Fläche
    c.forward(SIDE)
    c.right(SIDE)
    c.back(SIDE)
    c.left(SIDE)

    # senkrechte Kante hoch
    c.up(SIDE)

    # obere Fläche
    c.forward(SIDE)
    c.right(SIDE)
    c.back(SIDE)
    c.left(SIDE)

    # wieder runter
    c.down(SIDE)

    c.land()


def main():
    # gui=True → 3D-Fenster; speed=1.5 → 1,5x schneller als Echtzeit;
    # camera_follow=True → Kamera bleibt auf der Drohne (Maus: ziehen=drehen, Scroll=Zoom)
    c = DroneController(backend="sim", verbose=True,
                        backend_kwargs={"gui": True, "speed": 1.5, "camera_follow": True})
    print("Akku:", c.connect(), "%\n")
    try:
        fly_cube(c)
    finally:
        c.report()
        c.disconnect()


if __name__ == "__main__":
    main()
