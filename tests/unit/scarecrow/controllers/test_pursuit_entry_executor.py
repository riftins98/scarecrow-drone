from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scarecrow.controllers.pursuit.entry_executor import (
    advance_left_wall_by_local_distance,
)


def _position(north, east, down=-2.5):
    return SimpleNamespace(position=SimpleNamespace(north_m=north, east_m=east, down_m=down))


@pytest.mark.asyncio
async def test_planner_advance_uses_local_displacement(mock_lidar_scan):
    drone = MagicMock()
    drone.get_position = AsyncMock(
        side_effect=[
            _position(0.0, 0.0, -5.0),
            _position(0.0, 0.0, -5.0),
            _position(1.01, 0.0, -5.0),
        ]
    )
    drone.set_velocity = AsyncMock()
    drone.ground_z = 0.0

    lidar = MagicMock()
    scans = [
        mock_lidar_scan(front=8.0, left=2.0),
        mock_lidar_scan(front=8.0, left=2.0),
    ]
    lidar.get_scan = MagicMock(side_effect=scans)

    reason, advanced_m = await advance_left_wall_by_local_distance(
        drone,
        lidar,
        distance_m=1.0,
        wall_distance=2.0,
        target_alt_m=5.0,
        heading_yaw_deg=0.0,
        timeout_s=1.0,
        forward_speed=0.30,
        wall_follow_kp=0.75,
        wall_follow_kd=0.22,
        wall_follow_max_lateral=0.24,
        wall_follow_yaw_kp=2.0,
        wall_follow_max_yaw=8.0,
        altitude_down_speed_fn=lambda agl, target: (0.0, agl - target, True),
    )

    assert reason == "distance_reached"
    assert advanced_m >= 0.9
