"""Tests für die beschleunigungsbegrenzte Sollwert-Führung der Sim.

Hardware- und PyBullet-frei: motion_profile importiert nur math + numpy.
"""

import math

import numpy as np
import pytest

from tello_control.sim.motion_profile import VectorRamp, YawRamp, shortest_angle_diff

DT = 1.0 / 240.0
V_MAX, A_MAX = 0.6, 1.2


def _run(ramp, target, steps=4000):
    """Rampe bis Stillstand am Ziel laufen lassen; Positionen + Speeds sammeln."""
    positions, speeds = [], []
    for _ in range(steps):
        positions.append(np.array(ramp.advance(target, DT), dtype=float, copy=True))
        speeds.append(ramp.speed)
        if ramp.speed == 0.0 and np.allclose(positions[-1], target, atol=1e-9):
            break
    return positions, speeds


def test_vector_ramp_reaches_target_exactly():
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    pos, _ = _run(r, [0.3, 0.0, 0.0])
    assert np.allclose(pos[-1], [0.3, 0.0, 0.0], atol=1e-9)
    assert r.speed == 0.0


def test_vector_ramp_never_overshoots():
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    pos, _ = _run(r, [0.3, 0.0, 0.0])
    xs = [p[0] for p in pos]
    assert max(xs) <= 0.3 + 1e-12
    # monoton: der Sollwert läuft nie rückwärts
    assert all(b >= a - 1e-12 for a, b in zip(xs, xs[1:]))


def test_vector_ramp_respects_acceleration_limit():
    """Das war der Bug: der alte Sollwert sprang in einem Schritt auf v_max."""
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    _, speeds = _run(r, [2.0, 0.0, 0.0])
    assert speeds[0] <= A_MAX * DT + 1e-12          # kein Geschwindigkeitssprung
    # Gilt lückenlos, auch beim Landen auf dem Ziel: die Restgeschwindigkeit wird
    # mit a_max abgebaut statt hart genullt.
    for a, b in zip(speeds, speeds[1:]):
        assert abs(b - a) <= A_MAX * DT + 1e-9


def test_vector_ramp_respects_velocity_limit():
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    _, speeds = _run(r, [5.0, 0.0, 0.0])
    assert max(speeds) <= V_MAX + 1e-12


def test_vector_ramp_decelerates_before_arrival():
    """Am Ziel muss die Geschwindigkeit null sein, nicht abgeschnitten werden."""
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    _, speeds = _run(r, [2.0, 0.0, 0.0])
    peak = max(speeds)
    assert speeds[-1] == 0.0
    # Abbremsphase existiert: die letzten Schritte liegen deutlich unter dem Peak
    assert speeds[-5] < peak


def test_vector_ramp_short_move_is_triangular():
    """Zu kurz für v_max: Dreiecksprofil, Peak unter dem Limit."""
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    _, speeds = _run(r, [0.05, 0.0, 0.0])
    assert 0.0 < max(speeds) < V_MAX


def test_vector_ramp_tracks_moving_target():
    """RC-Modus: Ziel wandert kontinuierlich, Rampe folgt mit konstantem Nachlauf.

    Die Rampe ist ein Ratenbegrenzer, kein Prädiktor. Im eingeschwungenen Zustand
    gilt v_ziel = sqrt(2*a*dist), der Abstand bleibt also stehen bei
    dist = v²/(2a) = 0.4²/2.4 ≈ 6.7 cm. Das ist gewollt und beschränkt, nicht Drift.
    """
    v_target = 0.4
    r = VectorRamp([0, 0, 0], V_MAX, A_MAX)
    target = np.zeros(3)
    for _ in range(1200):                       # 5 s bei 240 Hz
        target = target + np.array([v_target * DT, 0, 0])
        r.advance(target, DT)

    expected_lag = v_target**2 / (2.0 * A_MAX)
    assert target[0] - r.pos[0] == pytest.approx(expected_lag, abs=0.01)
    assert r.speed == pytest.approx(v_target, abs=0.01)   # läuft mit, driftet nicht


@pytest.mark.parametrize("target,expected", [
    (math.radians(10), math.radians(10)),
    (math.radians(350), math.radians(-10)),     # kürzester Weg: rückwärts
    (math.radians(180), math.radians(180)),
])
def test_shortest_angle_diff(target, expected):
    assert shortest_angle_diff(target, 0.0) == pytest.approx(expected, abs=1e-9)


def test_yaw_ramp_takes_short_way_around():
    """Von 350° nach 10° sind es +20°, nicht -340°."""
    r = YawRamp(math.radians(350), math.radians(90), math.radians(180))
    start = r.yaw
    r.advance(math.radians(370), DT)            # 370° == 10°
    assert r.yaw > start                        # dreht vorwärts, nicht 340° zurück


def test_yaw_ramp_reaches_target_and_stops():
    r = YawRamp(0.0, math.radians(90), math.radians(180))
    for _ in range(4000):
        r.advance(math.radians(90), DT)
        if r.speed == 0.0 and r.yaw == pytest.approx(math.radians(90)):
            break
    assert r.yaw == pytest.approx(math.radians(90), abs=1e-9)
    assert r.speed == 0.0


def test_ramps_are_noop_when_already_at_target():
    r = VectorRamp([1, 2, 3], V_MAX, A_MAX)
    r.advance([1, 2, 3], DT)
    assert r.speed == 0.0
    assert np.allclose(r.pos, [1, 2, 3])
