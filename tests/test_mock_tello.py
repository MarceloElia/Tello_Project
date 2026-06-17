"""MockTello — the hardware-free software drone that backs both the mock and the
simulation backends. Tests cover pose tracking, SDK safety bounds and logging.
"""

import math

import pytest

from tello_control.core.mock_tello import MockTello, TelloException


def _airborne():
    drone = MockTello(verbose=False)
    drone.connect()
    drone.takeoff()
    return drone


def test_connect_and_takeoff():
    drone = MockTello(verbose=False)
    assert not drone.connected
    drone.connect()
    assert drone.connected
    drone.takeoff()
    assert drone.flying
    assert drone.get_height() == 100


def test_move_requires_takeoff():
    drone = MockTello(verbose=False)
    drone.connect()
    with pytest.raises(TelloException):
        drone.move_forward(50)


def test_command_before_connect_fails():
    drone = MockTello(verbose=False)
    with pytest.raises(TelloException):
        drone.takeoff()


def test_forward_moves_along_y_at_zero_yaw():
    drone = _airborne()
    y0 = drone.y
    drone.move_forward(100)
    assert math.isclose(drone.y - y0, 100, abs_tol=1e-6)
    assert math.isclose(drone.x, 0, abs_tol=1e-6)


def test_right_moves_along_x_at_zero_yaw():
    drone = _airborne()
    drone.move_right(100)
    assert math.isclose(drone.x, 100, abs_tol=1e-6)


def test_yaw_then_forward_changes_direction():
    drone = _airborne()
    drone.rotate_clockwise(90)
    assert drone.yaw % 360 == 90
    drone.move_forward(100)
    # facing +90° (to the right) -> forward now increases x, not y
    assert math.isclose(drone.x, 100, abs_tol=1e-3)
    assert math.isclose(drone.y, 0, abs_tol=1e-3)


@pytest.mark.parametrize("dist", [10, 0, 501, 1000])
def test_distance_bounds(dist):
    drone = _airborne()
    with pytest.raises(TelloException):
        drone.move_forward(dist)


@pytest.mark.parametrize("angle", [0, 361, 720])
def test_angle_bounds(angle):
    drone = _airborne()
    with pytest.raises(TelloException):
        drone.rotate_clockwise(angle)


def test_land_resets_height_and_flying():
    drone = _airborne()
    drone.move_up(50)
    drone.land()
    assert not drone.flying
    assert drone.get_height() == 0


def test_log_records_commands():
    drone = _airborne()
    drone.move_forward(50)
    cmds = [entry["cmd"] for entry in drone.log]
    assert "connect" in cmds
    assert "takeoff" in cmds
    assert "forward 50" in cmds


def test_battery_drains():
    drone = MockTello(verbose=False, start_battery=86)
    drone.connect()
    drone.takeoff()
    assert drone.get_battery() < 86
