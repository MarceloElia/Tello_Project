"""MockTello RC/velocity control — send_rc_control clamping + tick integration.

Deterministic: tick(dt=...) is driven with an explicit dt, no wall clock.
"""

import math

import pytest

from tello_control.core.mock_tello import MockTello, TelloException
from tello_control.core.constants import RC_MAX


def _airborne():
    drone = MockTello(verbose=False)
    drone.connect()
    drone.takeoff()
    return drone


def test_send_rc_requires_flying():
    drone = MockTello(verbose=False)
    drone.connect()
    with pytest.raises(TelloException):
        drone.send_rc_control(0, 40, 0, 0)


def test_send_rc_clamps_out_of_range():
    drone = _airborne()
    drone.send_rc_control(500, -500, 999, -999)
    assert drone._rc == (RC_MAX, -RC_MAX, RC_MAX, -RC_MAX)


def test_forward_velocity_increases_y():
    drone = _airborne()
    y0 = drone.y
    drone.send_rc_control(0, 40, 0, 0)   # fb = forward
    drone.tick(dt=1.0)
    assert drone.y > y0
    assert math.isclose(drone.x, 0.0, abs_tol=1e-6)


def test_right_velocity_increases_x():
    drone = _airborne()
    x0 = drone.x
    drone.send_rc_control(40, 0, 0, 0)   # lr = right
    drone.tick(dt=1.0)
    assert drone.x > x0


def test_up_velocity_increases_z():
    drone = _airborne()
    z0 = drone.z
    drone.send_rc_control(0, 0, 40, 0)   # ud = up
    drone.tick(dt=1.0)
    assert drone.z > z0


def test_yaw_velocity_rotates():
    drone = _airborne()
    drone.send_rc_control(0, 0, 0, 30)   # yaw = clockwise
    drone.tick(dt=1.0)
    assert math.isclose(drone.yaw % 360, 30.0, abs_tol=1e-6)


def test_zero_setpoint_holds_pose():
    drone = _airborne()
    drone.send_rc_control(0, 0, 0, 0)
    pose = (drone.x, drone.y, drone.z, drone.yaw)
    drone.tick(dt=1.0)
    assert (drone.x, drone.y, drone.z, drone.yaw) == pose


def test_tick_noop_on_ground():
    drone = MockTello(verbose=False)
    drone.connect()
    # not flying → tick integrates nothing even if a setpoint somehow exists
    drone._rc = (40, 40, 40, 40)
    drone.tick(dt=1.0)
    assert (drone.x, drone.y, drone.z) == (0.0, 0.0, 0.0)
