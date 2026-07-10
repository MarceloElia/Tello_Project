"""Tests für die Tastenzuordnung der Sim-Tastatursteuerung (kein PyBullet nötig)."""

import pytest

from tello_control.core.constants import RC_CRUISE, RC_MAX, RC_MIN
from tello_control.sim.keyboard_map import HOVER, keys_to_velocity


def test_no_keys_is_hover():
    assert keys_to_velocity(set()) == (0, 0, 0, 0)


@pytest.mark.parametrize("key,expected", [
    ("w", (0,  RC_CRUISE, 0, 0)),
    ("s", (0, -RC_CRUISE, 0, 0)),
    ("d", (RC_CRUISE,  0, 0, 0)),
    ("a", (-RC_CRUISE, 0, 0, 0)),
    ("r", (0, 0,  RC_CRUISE, 0)),
    ("f", (0, 0, -RC_CRUISE, 0)),
    ("e", (0, 0, 0,  RC_CRUISE)),
    ("z", (0, 0, 0, -RC_CRUISE)),
])
def test_single_key_maps_to_one_axis(key, expected):
    assert keys_to_velocity({key}) == expected


def test_opposing_keys_cancel():
    assert keys_to_velocity({"w", "s"}) == (0, 0, 0, 0)
    assert keys_to_velocity({"a", "d"}) == (0, 0, 0, 0)


def test_diagonal_is_not_faster_than_a_single_axis():
    """w+d darf nicht sqrt(2)-mal schneller sein als w allein."""
    lr, fb, _, _ = keys_to_velocity({"w", "d"})
    assert (lr, fb) == (RC_CRUISE, RC_CRUISE)
    assert abs(lr) <= RC_CRUISE and abs(fb) <= RC_CRUISE


def test_hover_key_beats_everything():
    assert keys_to_velocity({"w", "d", "r", HOVER}) == (0, 0, 0, 0)


def test_unknown_keys_are_ignored():
    assert keys_to_velocity({"x", "7", "ü"}) == (0, 0, 0, 0)
    assert keys_to_velocity({"w", "x"}) == (0, RC_CRUISE, 0, 0)


def test_output_stays_inside_sdk_rc_range():
    for keys in ({"w"}, {"w", "d", "r", "e"}, {"s", "a", "f", "z"}):
        for axis in keys_to_velocity(keys):
            assert RC_MIN <= axis <= RC_MAX


def test_custom_cruise_speed_is_respected():
    assert keys_to_velocity({"w"}, cruise=100) == (0, 100, 0, 0)
