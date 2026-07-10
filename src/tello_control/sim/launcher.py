"""
tello_control.sim.launcher

Test-Launcher für die Simulation. Startet die einzelnen Programme gegen die
PyBullet-Sim aus einem Menü – jedes in einem eigenen Prozess (damit sich z.B.
OpenCV und PyAV nicht im selben Prozess ins Gehege kommen).

Voraussetzung: conda-Env 'tello-sim' aktiv, Paket installiert (pip install -e . --no-deps).
    conda activate tello-sim
    cd ~/Projects/tello-projekt
    python -m tello_control.sim.launcher

Menü:
    1  Würfel-Demo               (tello_control.sim.demo)
    2  Regelungs-Labor / PID     (tello_control.sim.control_lab)
    3  Gestensteuerung gegen Sim (tello_control.gesture.app --sim)
    4  Sprachsteuerung gegen Sim (tello_control.voice.app --sim)
    5  Sprachsteuerung, Dauerhören (tello_control.voice.app --sim --continuous)
    6  Tastatursteuerung + Regler-Panel (tello_control.sim.keyboard_control)
    q  beenden
"""

import sys
import subprocess

OPTIONS = {
    "1": ("Würfel-Demo",                 ["-m", "tello_control.sim.demo"]),
    "2": ("Regelungs-Labor / PID",       ["-m", "tello_control.sim.control_lab"]),
    "3": ("Gestensteuerung gegen Sim",   ["-m", "tello_control.gesture.app", "--sim"]),
    "4": ("Sprachsteuerung gegen Sim",   ["-m", "tello_control.voice.app", "--sim"]),
    "5": ("Sprachsteuerung Dauerhören",  ["-m", "tello_control.voice.app", "--sim", "--continuous"]),
    "6": ("Tastatursteuerung + Regler",  ["-m", "tello_control.sim.keyboard_control"]),
}


def menu():
    print("\n" + "=" * 44)
    print("  Tello Simulation – Test-Launcher")
    print("=" * 44)
    for key, (label, _) in OPTIONS.items():
        print(f"  {key}  {label}")
    print("  q  beenden")
    print("-" * 44)


def main():
    while True:
        menu()
        choice = input("Auswahl: ").strip().lower()
        if choice == "q":
            break
        if choice not in OPTIONS:
            print("  Ungültige Auswahl.")
            continue

        label, args = OPTIONS[choice]
        print(f"\n▶  Starte: {label}\n")
        try:
            subprocess.run([sys.executable, *args])
        except KeyboardInterrupt:
            print("\n  (abgebrochen)")
        print(f"\n◀  '{label}' beendet – zurück im Menü.")

    print("\nLauncher beendet.")


if __name__ == "__main__":
    main()
