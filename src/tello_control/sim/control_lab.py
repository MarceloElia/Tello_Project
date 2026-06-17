"""
control_lab.py

Regelungs-Labor (das alte A3.5, jetzt im Sim machbar).

Was hier möglich ist und beim echten Tello NICHT ging: direkt an den PID-Gains
des Positionsreglers drehen und das Verhalten messen. Wir fliegen einen 1-m-Sprung
in X (Sprungantwort) mit verschiedenen Proportional-Gains und vergleichen
Überschwingen / Einschwingen.

Starten (conda-Env tello-sim, aus dem Projektordner):
    conda activate tello-sim
    python -m tello_control.sim.control_lab

Ergebnis: Plot 'results/control_lab_step.png' + Kennzahlen im Terminal.
"""

import sys
import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import matplotlib
matplotlib.use("Agg")            # ohne Display, speichert PNG
import matplotlib.pyplot as plt

from gym_pybullet_drones.envs.CtrlAviary import CtrlAviary
from gym_pybullet_drones.control.DSLPIDControl import DSLPIDControl
from gym_pybullet_drones.utils.enums import DroneModel

CTRL = 240
START = np.array([0.0, 0.0, 1.0])    # Start im Schwebeflug auf 1 m
TARGET = np.array([1.0, 0.0, 1.0])   # 1-m-Sprung in X


def step_response(p_xy=0.4, sim_time=4.0, gui=False):
    """Fliegt den X-Sprung mit gegebenem P-Gain (x/y) und loggt die Trajektorie."""
    env = CtrlAviary(drone_model=DroneModel.CF2X, num_drones=1,
                     initial_xyzs=START.reshape(1, 3),
                     pyb_freq=CTRL, ctrl_freq=CTRL, gui=gui)
    ctrl = DSLPIDControl(drone_model=DroneModel.CF2X)
    # Proportional-Gain für x/y überschreiben (z unverändert lassen)
    ctrl.P_COEFF_FOR = np.array([p_xy, p_xy, 1.25])

    obs, _ = env.reset()
    n = int(sim_time * CTRL)
    ts = np.zeros(n)
    xs = np.zeros(n)
    for i in range(n):
        rpm = ctrl.computeControlFromState(
            control_timestep=1.0 / CTRL, state=obs[0], target_pos=TARGET)[0]
        obs, _, _, _, _ = env.step(rpm.reshape(1, 4))
        ts[i] = i / CTRL
        xs[i] = obs[0][0]
    env.close()
    return ts, xs


def metrics(ts, xs, target=1.0):
    """Überschwingen (%) und Einschwingzeit (in 5%-Band) berechnen."""
    overshoot = max(0.0, (xs.max() - target) / target * 100)
    band = 0.05 * target
    settle_t = ts[-1]
    for i in range(len(xs)):
        if np.all(np.abs(xs[i:] - target) <= band):
            settle_t = ts[i]
            break
    return overshoot, settle_t


def main():
    experiments = {
        "träge  (P=0.20)":      0.20,
        "default (P=0.40)":     0.40,
        "aggressiv (P=0.90)":   0.90,
    }

    plt.figure(figsize=(8, 5))
    plt.axhline(TARGET[0], color="gray", ls="--", lw=1, label="Ziel (1 m)")
    plt.axhspan(0.95, 1.05, color="gray", alpha=0.12)

    print("\n  X-Sprungantwort (0 → 1 m), verschiedene P-Gains")
    print("  " + "-" * 50)
    print(f"  {'Konfiguration':<22}{'Überschwingen':>14}{'Einschwingen':>14}")
    print("  " + "-" * 50)
    for label, p in experiments.items():
        ts, xs = step_response(p_xy=p)
        ov, st = metrics(ts, xs)
        print(f"  {label:<22}{ov:>12.1f} %{st:>12.2f} s")
        plt.plot(ts, xs, label=label)
    print("  " + "-" * 50)

    plt.xlabel("Zeit [s]")
    plt.ylabel("X-Position [m]")
    plt.title("PID-Sprungantwort im Sim (gym-pybullet-drones)")
    plt.legend()
    plt.grid(alpha=0.3)
    out_dir = os.path.join(os.getcwd(), "results")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "control_lab_step.png")
    plt.savefig(out, dpi=120, bbox_inches="tight")
    print(f"\n  Plot gespeichert: {out}\n")


if __name__ == "__main__":
    main()
