"""GestureToCommand — debounce + cooldown + gesture->command mapping.

A FakeController records calls instead of touching a drone, so this runs without
any hardware. (Importing the gesture package pulls in MediaPipe/OpenCV, which are
core dependencies of the project.)
"""

import pytest

from tello_control.gesture.detector import Gesture
from tello_control.gesture.command_map import GestureToCommand, STABLE_FRAMES


class FakeController:
    """Captures method calls as (name, args) tuples."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _record(*args):
            self.calls.append((name, args))
        return _record


def _feed_repeated(commander, gesture, n):
    last = None
    for _ in range(n):
        last = commander.feed(gesture)
    return last


def test_requires_stable_frames_before_dispatch():
    ctrl = FakeController()
    cmd = GestureToCommand(ctrl, verbose=False)
    # one frame short of the threshold -> nothing fires
    result = _feed_repeated(cmd, Gesture.THUMBS_UP, STABLE_FRAMES - 1)
    assert result is None
    assert ctrl.calls == []
    # the threshold-th identical frame fires
    result = cmd.feed(Gesture.THUMBS_UP)
    assert result == "up"
    assert ("up", (30,)) in ctrl.calls


def test_changing_gesture_resets_streak():
    ctrl = FakeController()
    cmd = GestureToCommand(ctrl, verbose=False)
    _feed_repeated(cmd, Gesture.THUMBS_UP, STABLE_FRAMES - 1)
    cmd.feed(Gesture.PEACE)              # different gesture resets the streak
    assert ctrl.calls == []


def test_cooldown_blocks_immediate_refire():
    ctrl = FakeController()
    cmd = GestureToCommand(ctrl, verbose=False)
    assert _feed_repeated(cmd, Gesture.THUMBS_UP, STABLE_FRAMES) == "up"
    # immediately after dispatch we are in cooldown -> no new command
    assert _feed_repeated(cmd, Gesture.THUMBS_UP, STABLE_FRAMES) is None


@pytest.mark.parametrize(
    "gesture, expected_call",
    [
        (Gesture.THUMBS_UP, ("up", (30,))),
        (Gesture.THUMBS_DOWN, ("down", (30,))),
        (Gesture.POINT_FORWARD, ("forward", (30,))),
        (Gesture.POINT_LEFT, ("left", (30,))),
        (Gesture.POINT_RIGHT, ("right", (30,))),
        (Gesture.PEACE, ("back", (30,))),
        (Gesture.OPEN_HAND, ("land", ())),
    ],
)
def test_gesture_mapping(gesture, expected_call):
    ctrl = FakeController()
    cmd = GestureToCommand(ctrl, verbose=False)
    _feed_repeated(cmd, gesture, STABLE_FRAMES)
    assert expected_call in ctrl.calls


def test_fist_is_hover_no_controller_call():
    ctrl = FakeController()
    cmd = GestureToCommand(ctrl, verbose=False)
    assert _feed_repeated(cmd, Gesture.FIST, STABLE_FRAMES) == "hover"
    assert ctrl.calls == []
