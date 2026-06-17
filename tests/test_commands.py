"""Validation layer for the voice pipeline (tello_control.voice.commands).

These tests guard the safety contract: a command list reaches the drone only if
EVERY command is valid. No hardware, no LLM — pure logic.
"""

import pytest

from tello_control.voice.commands import (
    Command,
    ValidationError,
    validate_command,
    validate_list,
)


def test_valueless_actions():
    for action in ("takeoff", "land", "emergency"):
        cmd = validate_command({"action": action})
        assert cmd == Command(action=action, value=None)


def test_valueless_action_ignores_extra_value():
    # takeoff/land/emergency must never carry a value, even if one is supplied.
    assert validate_command({"action": "takeoff", "value": 100}).value is None


def test_distance_command_ok():
    assert validate_command({"action": "forward", "value": 100}) == Command("forward", 100)


def test_angle_command_ok():
    assert validate_command({"action": "rotate_cw", "value": 90}) == Command("rotate_cw", 90)


def test_float_value_is_rounded_to_int():
    assert validate_command({"action": "up", "value": 49.6}).value == 50


@pytest.mark.parametrize(
    "raw",
    [
        {"action": "fly_to_moon"},               # 1. unknown action
        {"action": "forward"},                   # 2. missing required value
        {"action": "forward", "value": 10},      # 3. below min distance (20)
        {"action": "forward", "value": 600},     # 4. above max distance (500)
        {"action": "rotate_cw", "value": 0},     # 5. below min angle (1)
        {"action": "rotate_cw", "value": 400},   # 6. above max angle (360)
        {"action": "forward", "value": True},    # 7. bool is not a valid number
        {"action": "forward", "value": "ten"},   # 8. string is not a number
    ],
)
def test_invalid_commands_rejected(raw):
    with pytest.raises(ValidationError):
        validate_command(raw)


def test_validate_list_ok():
    payload = {"commands": [{"action": "takeoff"}, {"action": "forward", "value": 200}]}
    cmds = validate_list(payload)
    assert [str(c) for c in cmds] == ["takeoff", "forward 200"]


@pytest.mark.parametrize(
    "payload",
    [
        {},                                  # no 'commands' field
        {"commands": []},                    # empty list
        {"commands": "takeoff"},             # not a list
        {"commands": [{"action": "nope"}]},  # one invalid -> whole list rejected
    ],
)
def test_validate_list_rejected(payload):
    with pytest.raises(ValidationError):
        validate_list(payload)


def test_one_bad_command_aborts_whole_list():
    # A valid first command must not sneak through if a later one is invalid.
    payload = {"commands": [{"action": "takeoff"}, {"action": "forward", "value": 5}]}
    with pytest.raises(ValidationError):
        validate_list(payload)
