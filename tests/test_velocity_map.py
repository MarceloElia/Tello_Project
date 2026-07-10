"""velocity_map — gesture->velocity mapping + VelocityBlender smoothing.

Pure logic, no hardware. Mirrors the test_gesture_command_map.py style.
"""

import pytest

from tello_control.core.constants import RC_CRUISE
from tello_control.gesture.detector import Gesture
from tello_control.gesture.velocity_map import (
    gesture_to_velocity, VelocityBlender, MAX_STEP,
)


@pytest.mark.parametrize("gesture, expected", [
    (Gesture.POINT_FORWARD, (0,          RC_CRUISE,  0,          0)),
    (Gesture.PEACE,         (0,         -RC_CRUISE,  0,          0)),
    (Gesture.THUMBS_UP,     (0,          0,          RC_CRUISE,  0)),
    (Gesture.THUMBS_DOWN,   (0,          0,         -RC_CRUISE,  0)),
    (Gesture.POINT_RIGHT,   (RC_CRUISE,  0,          0,          0)),
    (Gesture.POINT_LEFT,    (-RC_CRUISE, 0,          0,          0)),
    (Gesture.FIST,          (0,          0,          0,          0)),
])
def test_gesture_velocity_mapping(gesture, expected):
    assert gesture_to_velocity(gesture) == expected


@pytest.mark.parametrize("gesture", [Gesture.UNKNOWN, Gesture.OPEN_HAND])
def test_unmapped_gestures_are_hover(gesture):
    """UNKNOWN and OPEN_HAND (discrete land) both map to a zero setpoint."""
    assert gesture_to_velocity(gesture) == (0, 0, 0, 0)


def test_blender_ramps_by_at_most_max_step_per_frame():
    b = VelocityBlender()
    target = (0, RC_CRUISE, 0, 0)
    prev = 0
    for _ in range(3):
        _, fb, _, _ = b.update(target)
        assert fb - prev <= MAX_STEP
        prev = fb


def test_blender_reaches_target_and_holds():
    b = VelocityBlender()
    target = (0, RC_CRUISE, 0, 0)
    for _ in range(20):
        out = b.update(target)
    assert out == target
    assert b.update(target) == target   # stays put once reached


def test_blender_decays_to_zero_on_hover():
    b = VelocityBlender()
    for _ in range(20):
        b.update((0, RC_CRUISE, 0, 0))
    for _ in range(20):
        out = b.update((0, 0, 0, 0))
    assert out == (0, 0, 0, 0)


def test_single_offframe_barely_perturbs_output():
    """A one-frame spurious gesture only nudges velocity by <= MAX_STEP, then reverts."""
    b = VelocityBlender()
    # steady hover
    b.update((0, 0, 0, 0))
    # one stray full-speed frame
    stray = b.update((RC_CRUISE, 0, 0, 0))
    assert abs(stray[0]) <= MAX_STEP
    # back to hover next frame → returns to (near) zero
    recovered = b.update((0, 0, 0, 0))
    assert recovered == (0, 0, 0, 0)
