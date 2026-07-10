"""Tests für die Spezifikation des Sim-Regler-Panels (kein PyBullet nötig)."""

import numpy as np
import pytest

from tello_control.sim.tuning_panel import (
    BUTTONS, SPECS, Spec, clamp, defaults, pid_arrays,
)


def test_spec_keys_are_unique():
    keys = [s.key for s in SPECS]
    assert len(keys) == len(set(keys))


def test_button_names_do_not_collide_with_slider_keys():
    assert not (set(BUTTONS) & {s.key for s in SPECS})


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.key)
def test_default_lies_inside_its_range(spec: Spec):
    assert spec.lo <= spec.default <= spec.hi
    assert spec.lo < spec.hi


def test_defaults_match_the_shipped_values():
    """Die Slider dürfen beim Start nichts verstellen."""
    d = defaults()
    assert d["cruise_ms"] == 0.60      # CRUISE_MS
    assert d["max_acc"] == 1.20        # MAX_ACC
    assert d["yaw_rate"] == 90.0       # YAW_RATE (Grad)
    assert d["p_xy"] == 0.40           # DSLPIDControl P_COEFF_FOR[0]
    assert d["p_z"] == 1.25            # DSLPIDControl P_COEFF_FOR[2]
    assert d["rc_cruise"] == 40.0      # RC_CRUISE


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.key)
def test_clamp_bounds_both_sides(spec: Spec):
    assert clamp(spec, spec.lo - 1e6) == spec.lo
    assert clamp(spec, spec.hi + 1e6) == spec.hi
    assert clamp(spec, spec.default) == spec.default


def test_pid_arrays_shape_and_axis_order():
    a = pid_arrays(p_xy=0.5, p_z=1.5, i_xy=0.1, d_xy=0.3, d_z=0.7)
    assert set(a) == {"P_COEFF_FOR", "I_COEFF_FOR", "D_COEFF_FOR"}
    for arr in a.values():
        assert arr.shape == (3,)
        assert arr.dtype == float
    np.testing.assert_allclose(a["P_COEFF_FOR"], [0.5, 0.5, 1.5])
    np.testing.assert_allclose(a["D_COEFF_FOR"], [0.3, 0.3, 0.7])
    assert a["I_COEFF_FOR"][0] == a["I_COEFF_FOR"][1] == 0.1


def test_pid_arrays_defaults_reproduce_dslpid_defaults():
    """Slider auf Default => exakt die Gains, mit denen DSLPIDControl ausgeliefert wird."""
    d = defaults()
    a = pid_arrays(d["p_xy"], d["p_z"], d["i_xy"], d["d_xy"], d["d_z"])
    np.testing.assert_allclose(a["P_COEFF_FOR"], [0.4, 0.4, 1.25])
    np.testing.assert_allclose(a["I_COEFF_FOR"], [0.05, 0.05, 0.05])
    np.testing.assert_allclose(a["D_COEFF_FOR"], [0.2, 0.2, 0.5])


def test_torque_gains_are_not_exposed():
    """P/I/D_COEFF_TOR bleiben absichtlich draußen: destabilisieren die Lageregelung."""
    assert not any("tor" in s.key.lower() for s in SPECS)
    assert "P_COEFF_TOR" not in pid_arrays(0.4, 1.25, 0.05, 0.2, 0.5)
