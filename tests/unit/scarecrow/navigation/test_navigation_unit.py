"""UT-20: NavigationUnit tests. Mocks Drone and LidarSource."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scarecrow.controllers.distance_stabilizer import DistanceTargets


def _make_drone():
    drone = MagicMock()
    drone.set_velocity = AsyncMock()
    drone.system = MagicMock()
    return drone


def _make_lidar_source(scan):
    lidar = MagicMock()
    lidar.get_scan = MagicMock(return_value=scan)
    return lidar


async def test_wall_follow_stops_when_front_detected(mock_lidar_scan):
    """With front wall very close, wall_follow should complete quickly."""
    drone = _make_drone()
    # Scan shows left wall at 2m (target), front wall at 1m (stop)
    scan = mock_lidar_scan(front=1.0, left=2.0)
    lidar = _make_lidar_source(scan)

    from scarecrow.navigation.navigation_unit import NavigationUnit
    nav = NavigationUnit(drone, lidar)

    result = await nav.wall_follow(
        side="left",
        target_distance=2.0,
        front_stop_distance=2.0,
        timeout=5.0,
    )
    assert result is True
    # Should have sent at least one velocity command and a final zero
    assert drone.set_velocity.await_count >= 1


async def test_wall_follow_times_out_when_no_stop(mock_lidar_scan):
    """Open field -- front never triggers stop, should timeout cleanly."""
    drone = _make_drone()
    scan = mock_lidar_scan(front=10.0, left=2.0)
    lidar = _make_lidar_source(scan)

    from scarecrow.navigation.navigation_unit import NavigationUnit
    nav = NavigationUnit(drone, lidar)

    result = await nav.wall_follow(
        side="left",
        target_distance=2.0,
        front_stop_distance=2.0,
        timeout=0.2,  # very short so test runs fast
    )
    assert result is False


async def test_stabilize_delegates(mock_lidar_scan):
    drone = _make_drone()
    lidar = _make_lidar_source(mock_lidar_scan(front=5.0))

    with patch("scarecrow.navigation.navigation_unit.lidar_stabilize",
               new=AsyncMock(return_value=True)) as mock_stab:
        from scarecrow.navigation.navigation_unit import NavigationUnit
        nav = NavigationUnit(drone, lidar)
        targets = DistanceTargets(front=3.0)
        result = await nav.stabilize(targets)
        assert result is True
        mock_stab.assert_awaited_once()


async def test_rotate_delegates():
    drone = _make_drone()
    lidar = MagicMock()

    with patch("scarecrow.navigation.navigation_unit.rotate_90",
               new=AsyncMock(return_value=True)) as mock_rot:
        from scarecrow.navigation.navigation_unit import NavigationUnit
        nav = NavigationUnit(drone, lidar)
        result = await nav.rotate(direction="right")
        assert result is True
        mock_rot.assert_awaited_once()


async def test_circuit_runs_all_legs(mock_lidar_scan):
    drone = _make_drone()
    scan = mock_lidar_scan(front=1.0, left=2.0)
    lidar = _make_lidar_source(scan)

    with patch("scarecrow.navigation.navigation_unit.rotate_90",
               new=AsyncMock(return_value=True)) as mock_rot:
        from scarecrow.navigation.navigation_unit import NavigationUnit
        nav = NavigationUnit(drone, lidar)
        result = await nav.circuit(num_legs=3, side="left", target_distance=2.0)
        assert result is True
        # 3 legs means 2 rotations between them
        assert mock_rot.await_count == 2


async def test_circuit_returns_false_on_leg_failure(mock_lidar_scan):
    drone = _make_drone()
    # Front stays open so wall_follow times out
    scan = mock_lidar_scan(front=10.0, left=2.0)
    lidar = _make_lidar_source(scan)

    from scarecrow.navigation.navigation_unit import NavigationUnit
    nav = NavigationUnit(drone, lidar)

    # Very short timeout -> wall_follow returns False on first leg
    nav_orig_wf = nav.wall_follow

    async def fast_wall_follow(**kwargs):
        kwargs["timeout"] = 0.1
        return await nav_orig_wf(**kwargs)

    nav.wall_follow = fast_wall_follow
    result = await nav.circuit(num_legs=2)
    assert result is False
