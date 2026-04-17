"""UT-21: Drone class tests. Mocks mavsdk.System."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scarecrow.controllers.wall_follow import VelocityCommand


@pytest.fixture
def fake_mavsdk_system():
    """Returns a MagicMock with all async MAVSDK methods stubbed."""
    sys = MagicMock()
    sys.connect = AsyncMock()
    sys.action.arm = AsyncMock()
    sys.action.disarm = AsyncMock()
    sys.action.takeoff = AsyncMock()
    sys.action.land = AsyncMock()
    sys.action.return_to_launch = AsyncMock()
    sys.action.set_takeoff_altitude = AsyncMock()
    sys.action.set_gps_global_origin = AsyncMock()
    sys.offboard.set_velocity_body = AsyncMock()
    sys.offboard.start = AsyncMock()
    sys.offboard.stop = AsyncMock()
    sys.param.get_param_int = AsyncMock()
    return sys


@pytest.fixture
def drone(fake_mavsdk_system):
    with patch("scarecrow.drone.System", return_value=fake_mavsdk_system):
        from scarecrow.drone import Drone
        d = Drone(system_address="udp://:14540")
        yield d


async def test_initial_state(drone):
    assert drone.mode == "sim"
    assert drone.is_armed is False
    assert drone.is_in_air is False
    assert drone.is_in_offboard is False
    assert drone.ground_z == 0.0


async def test_arm_sets_armed(drone):
    await drone.arm()
    assert drone.is_armed is True
    drone._system.action.arm.assert_awaited_once()


async def test_disarm_clears_armed(drone):
    await drone.arm()
    await drone.disarm()
    assert drone.is_armed is False


async def test_land_clears_in_air(drone):
    drone._in_air = True
    await drone.land()
    assert drone.is_in_air is False
    drone._system.action.land.assert_awaited_once()


async def test_set_velocity_converts_command(drone):
    cmd = VelocityCommand(forward_m_s=0.5, right_m_s=0.1, yawspeed_deg_s=10.0)
    await drone.set_velocity(cmd)
    drone._system.offboard.set_velocity_body.assert_awaited_once()
    # Verify the call had the right forward speed
    call_args = drone._system.offboard.set_velocity_body.call_args[0][0]
    assert call_args.forward_m_s == 0.5
    assert call_args.right_m_s == 0.1
    assert call_args.yawspeed_deg_s == 10.0


async def test_emergency_stop_calls_land_even_from_idle(drone):
    await drone.emergency_stop()
    drone._system.action.land.assert_awaited()


async def test_emergency_stop_stops_offboard_if_active(drone):
    drone._in_offboard = True
    await drone.emergency_stop()
    drone._system.offboard.stop.assert_awaited()
    assert drone.is_in_offboard is False


async def test_return_home_calls_rtl(drone):
    await drone.return_home()
    drone._system.action.return_to_launch.assert_awaited_once()


async def test_start_offboard_sends_zero_setpoint_first(drone):
    ok = await drone.start_offboard()
    assert ok is True
    assert drone.is_in_offboard is True
    # Initial zero setpoint before start()
    drone._system.offboard.set_velocity_body.assert_awaited()
    drone._system.offboard.start.assert_awaited_once()


async def test_start_offboard_failure_returns_false(drone):
    drone._system.offboard.start = AsyncMock(side_effect=RuntimeError("fail"))
    ok = await drone.start_offboard()
    assert ok is False
    assert drone.is_in_offboard is False


async def test_stop_offboard_when_not_active_is_safe(drone):
    await drone.stop_offboard()  # should not raise
    assert drone.is_in_offboard is False


async def test_set_ekf_origin_swallows_error(drone):
    drone._system.action.set_gps_global_origin = AsyncMock(side_effect=RuntimeError("already set"))
    await drone.set_ekf_origin()  # should not raise


async def test_verify_gps_denied_params_returns_true_on_correct_config(drone):
    """EKF2_GPS_CTRL=0, EKF2_OF_CTRL=1, SYS_HAS_GPS=0 -> True."""
    expected = {
        "EKF2_GPS_CTRL": 0,
        "EKF2_OF_CTRL": 1,
        "SYS_HAS_GPS": 0,
    }
    async def fake_get(name):
        return expected[name]
    drone._system.param.get_param_int = AsyncMock(side_effect=fake_get)
    ok = await drone.verify_gps_denied_params(verbose=False)
    assert ok is True


async def test_verify_gps_denied_params_returns_false_when_gps_enabled(drone):
    """EKF2_GPS_CTRL=1 (wrong) -> False."""
    wrong = {"EKF2_GPS_CTRL": 1, "EKF2_OF_CTRL": 1, "SYS_HAS_GPS": 0}
    async def fake_get(name):
        return wrong[name]
    drone._system.param.get_param_int = AsyncMock(side_effect=fake_get)
    ok = await drone.verify_gps_denied_params(verbose=False)
    assert ok is False


async def test_verify_gps_denied_params_returns_false_on_read_error(drone):
    drone._system.param.get_param_int = AsyncMock(side_effect=RuntimeError("connection lost"))
    ok = await drone.verify_gps_denied_params(verbose=False)
    assert ok is False
