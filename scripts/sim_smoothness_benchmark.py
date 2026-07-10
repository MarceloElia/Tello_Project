"""Misst, wie ruckartig die Sim-Drohne einen 30-cm-Schritt fliegt.

Aufruf (conda-Env tello-sim):
    python scripts/sim_smoothness_benchmark.py

Vergleicht drei Sollwert-Führungen, die alle denselben DSLPID-Regler speisen:

  sprung : Der Sollwert springt sofort aufs Ziel. So arbeitete `tick()` im
           kooperativen Modus — also Gesten-, Sprach- und Tastatursteuerung.
           Ein 30-cm-Stufeneingang, die härteste denkbare Anregung.
  alt    : Der Sollwert läuft ab dem ersten Schritt mit voller Geschwindigkeit los und
           schnappt am Ende aufs Ziel. So arbeitete `_sim_goto` (blockierender Modus).
  neu    : Beschleunigungsbegrenztes Trapezprofil (motion_profile.VectorRamp),
           jetzt in beiden Pfaden.

Gemessen wird an der *tatsächlichen* Drohnenposition aus der Physik, nicht am
Sollwert. Ruck (jerk) ist die Ableitung der Beschleunigung und das, was ein
Betrachter als "ruckelig" wahrnimmt.

Kein GUI, keine Hardware. Läuft nur dort, wo PyBullet installiert ist.
"""

from __future__ import annotations

import numpy as np

from tello_control.sim.motion_profile import VectorRamp
from tello_control.sim.pybullet_backend import (
    CRUISE_MS, CTRL_FREQ, MAX_ACC, PyBulletBackend,
)

DT = 1.0 / CTRL_FREQ
STEP_M = 0.30
STEPS = 900


def _fly(law: str) -> tuple[np.ndarray, float, float]:
    b = PyBulletBackend(verbose=False, gui=False, speed=0, camera_follow=False)
    b.connect()
    b.takeoff()

    start = b._obs[0][0:3].astype(float).copy()
    final = start + np.array([STEP_M, 0.0, 0.0])
    setpoint = start.copy()
    ramp = VectorRamp(start, CRUISE_MS, MAX_ACC)
    track = []

    for _ in range(STEPS):
        if law == "sprung":
            setpoint = final
        elif law == "alt":
            d = final - setpoint
            n = float(np.linalg.norm(d))
            step = CRUISE_MS * DT
            setpoint = final if n <= step else setpoint + d / n * step
        else:
            setpoint = ramp.advance(final, DT)
        b._step_physics(setpoint, 0.0, DT)
        track.append(float(b._obs[0][0]))

    b.end()
    return np.asarray(track), float(final[0]), float(start[0])


def main() -> int:
    print(f"\n30-cm-Schritt, PID unverändert, {CTRL_FREQ} Hz\n")
    hdr = f"{'Führung':<9}{'Überschwingen':>15}{'|a|max':>12}{'|Ruck|max':>14}{'RMS-Ruck':>12}"
    print(hdr)
    print("-" * len(hdr))

    for law in ("sprung", "alt", "neu"):
        x, target, start = _fly(law)
        vel = np.gradient(x, DT)
        acc = np.gradient(vel, DT)
        jerk = np.gradient(acc, DT)
        overshoot = (x.max() - target) / (target - start) * 100.0
        print(f"{law:<9}{overshoot:>13.2f} %{np.abs(acc).max():>10.2f} m/s²"
              f"{np.abs(jerk).max():>11.0f} m/s³{np.sqrt((jerk**2).mean()):>10.0f}")

    print("\nRuck ist die Ableitung der Beschleunigung — das, was das Auge als Ruckeln sieht.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
