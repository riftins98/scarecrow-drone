"""Mission map recording.

Replaces the record_map_sample coverage that lived in
tests/unit/scripts/flight/ before this logic moved into
scarecrow.navigation.mission_recorder.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scarecrow.navigation.mission_recorder import MissionRecorder


def _position(north, east, down=-2.5):
    return SimpleNamespace(
        position=SimpleNamespace(north_m=north, east_m=east, down_m=down)
    )


def _drone(*, positions, yaw=0.0):
    drone = MagicMock()
    drone.get_position = AsyncMock(side_effect=[_position(*pos) for pos in positions])
    drone.get_yaw = AsyncMock(return_value=yaw)
    drone.ground_z = 0.0
    return drone


def _lidar(scan):
    lidar = MagicMock()
    lidar.get_scan = MagicMock(return_value=scan)
    return lidar


@pytest.mark.asyncio
async def test_record_sample_records_all_cardinal_hits(mock_lidar_scan):
    recorder = MissionRecorder()
    recorder.start()
    drone = _drone(positions=[(10.0, 20.0)], yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=4.0, rear=3.0, left=2.0, right=5.0))

    ok = await recorder.record_sample(drone, lidar)

    assert ok is True
    assert len(recorder.mapper.points) == 1
    assert len(recorder.mapper.wall_points) == 4
    assert {"x": 14.0, "y": 20.0} in recorder.mapper.wall_points
    assert {"x": 7.0, "y": 20.0} in recorder.mapper.wall_points
    assert {"x": 10.0, "y": 18.0} in recorder.mapper.wall_points
    assert {"x": 10.0, "y": 25.0} in recorder.mapper.wall_points


@pytest.mark.asyncio
async def test_record_sample_rejects_partial_scan(mock_lidar_scan):
    """A scan missing a cardinal reading must not become a map sample."""
    recorder = MissionRecorder()
    recorder.start()
    drone = _drone(positions=[(0.0, 0.0)])
    lidar = _lidar(mock_lidar_scan(front=float("inf"), rear=3.0, left=2.0, right=5.0))

    ok = await recorder.record_sample(drone, lidar)

    assert ok is False
    assert recorder.mapper.points == []


@pytest.mark.asyncio
async def test_record_pose_event_captures_pose_and_extras():
    recorder = MissionRecorder()
    drone = _drone(positions=[(3.0, 4.0)], yaw=45.0)

    event = await recorder.record_pose_event(
        drone,
        event_type="pursuit_entry",
        label="Pursuit entry on leg 2",
        leg=2,
        reason="target_detected",
    )

    assert event["x"] == 3.0
    assert event["y"] == 4.0
    assert event["yaw_deg"] == 45.0
    assert event["leg"] == 2
    assert event["reason"] == "target_detected"
    assert recorder.events == [event]


def test_record_corner_ignores_near_duplicates():
    """A leg can start where the last one ended; the map must not blob."""
    recorder = MissionRecorder()
    recorder.start()

    assert recorder.record_corner(1.0, 1.0) is True
    assert recorder.record_corner(1.01, 1.01) is False
    assert recorder.record_corner(3.0, 3.0) is True
    assert len(recorder.mapper.corners) == 2


def test_has_content_is_false_before_anything_is_recorded():
    assert MissionRecorder().has_content is False
