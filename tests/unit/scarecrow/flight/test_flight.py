"""Flight orchestrator tests. Mocks Drone lifecycle methods."""
from unittest.mock import AsyncMock, MagicMock


def _make_drone(connect_ok=True, health_ok=True, takeoff_ok=True, offboard_ok=True):
    drone = MagicMock()
    drone.connect = AsyncMock(return_value=connect_ok)
    drone.wait_for_health = AsyncMock(return_value=health_ok)
    drone.set_ekf_origin = AsyncMock()
    drone.takeoff = AsyncMock(return_value=takeoff_ok)
    drone.start_offboard = AsyncMock(return_value=offboard_ok)
    drone.stop_offboard = AsyncMock()
    drone.land = AsyncMock()
    drone.emergency_stop = AsyncMock()
    drone.set_velocity = AsyncMock()
    drone.system = MagicMock()
    return drone


async def test_happy_path():
    drone = _make_drone()
    lidar = MagicMock()
    statuses: list[str] = []

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar, on_status=statuses.append)

    mission_ran = False

    async def mission(f):
        nonlocal mission_ran
        mission_ran = True

    result = await flight.run(mission, altitude=2.5)
    assert result is True
    assert mission_ran is True
    assert "completed" in statuses
    drone.takeoff.assert_awaited_once_with(2.5)
    drone.start_offboard.assert_awaited_once()
    drone.stop_offboard.assert_awaited_once()
    drone.land.assert_awaited_once()


async def test_failed_connection_aborts_early():
    drone = _make_drone(connect_ok=False)
    lidar = MagicMock()

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar)

    async def mission(f):
        raise AssertionError("mission should not run when connect fails")

    result = await flight.run(mission)
    assert result is False
    drone.takeoff.assert_not_awaited()


async def test_failed_health_check_aborts():
    drone = _make_drone(health_ok=False)
    lidar = MagicMock()

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar)

    async def mission(f):
        raise AssertionError("mission should not run")

    result = await flight.run(mission)
    assert result is False


async def test_failed_takeoff_aborts():
    drone = _make_drone(takeoff_ok=False)
    lidar = MagicMock()

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar)

    async def mission(f):
        raise AssertionError("mission should not run")

    result = await flight.run(mission)
    assert result is False


async def test_exception_in_mission_triggers_emergency_stop():
    drone = _make_drone()
    lidar = MagicMock()

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar)

    async def mission(f):
        raise RuntimeError("something went wrong mid-flight")

    import pytest
    with pytest.raises(RuntimeError, match="something went wrong"):
        await flight.run(mission)

    drone.emergency_stop.assert_awaited_once()
    assert flight.status == "failed"


async def test_status_callback_receives_lifecycle_events():
    drone = _make_drone()
    lidar = MagicMock()
    statuses: list[str] = []

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar, on_status=statuses.append)

    async def mission(f):
        pass

    await flight.run(mission)
    expected_stages = {"connecting", "health_check", "takeoff", "in_mission", "landing", "completed"}
    assert expected_stages <= set(statuses)


async def test_status_callback_exception_is_swallowed():
    """A raising status callback must not break the flight."""
    drone = _make_drone()
    lidar = MagicMock()

    def bad_callback(status):
        raise RuntimeError("callback broken")

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar, on_status=bad_callback)

    async def mission(f):
        pass

    result = await flight.run(mission)
    assert result is True  # Flight still succeeds


async def test_abort_calls_emergency_stop():
    drone = _make_drone()
    lidar = MagicMock()

    from scarecrow.flight.flight import Flight
    flight = Flight(drone, lidar)
    await flight.abort()
    assert flight.status == "aborted"
    drone.emergency_stop.assert_awaited_once()
