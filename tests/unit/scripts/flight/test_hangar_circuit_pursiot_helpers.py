from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.flight import hangar_circuit_pursiot as hangar


def _position(north, east):
    return SimpleNamespace(position=SimpleNamespace(north_m=north, east_m=east))


def _drone(*, positions, yaw=0.0):
    drone = MagicMock()
    drone.get_position = AsyncMock(side_effect=[_position(n, e) for n, e in positions])
    drone.get_yaw = AsyncMock(return_value=yaw)
    drone.set_velocity = AsyncMock()
    return drone


def _lidar(scan):
    lidar = MagicMock()
    lidar.get_scan = MagicMock(return_value=scan)
    return lidar


def test_arena_boundary_from_start_surrounds_start_pose():
    boundary = hangar._arena_boundary_from_start(
        x=0.0,
        y=0.0,
        yaw_deg=0.0,
        rear_distance=3.0,
        left_distance=3.0,
        front_distance=10.0,
        right_distance=7.0,
    )

    xs = [p["x"] for p in boundary]
    ys = [p["y"] for p in boundary]
    assert min(xs) == -3.0
    assert max(xs) == 10.0
    assert min(ys) == -3.0
    assert max(ys) == 7.0


def test_refine_boundary_from_route_samples_uses_stable_wall_evidence():
    boundary = [
        {"x": -4.3, "y": 2.9},
        {"x": -4.3, "y": -3.6},
        {"x": 7.7, "y": -3.6},
        {"x": 7.7, "y": 2.9},
    ]
    samples = [
        # Leg 1 front wall evidence: max X should be near 6.7, not 7.7.
        {
            "phase": "wall_follow",
            "x": 3.7,
            "y": -0.6,
            "yaw_deg": 0.0,
            "front_dist": 3.0,
            "rear_dist": 8.9,
            "left_dist": 3.0,
            "right_dist": 5.0,
        },
        {
            "phase": "wall_follow",
            "x": 3.8,
            "y": -0.5,
            "yaw_deg": 0.0,
            "front_dist": 2.9,
            "rear_dist": 9.0,
            "left_dist": 3.0,
            "right_dist": 5.0,
        },
        # Leg 3 left wall evidence: max Y should be near 4.4, not 2.9.
        {
            "phase": "wall_follow",
            "x": 1.0,
            "y": 1.4,
            "yaw_deg": 180.0,
            "front_dist": 5.0,
            "rear_dist": 6.0,
            "left_dist": 3.0,
            "right_dist": 5.0,
        },
        {
            "phase": "landing",
            "x": 3.6,
            "y": 1.5,
            "yaw_deg": 180.0,
            "front_dist": 8.8,
            "rear_dist": 3.0,
            "left_dist": 3.0,
            "right_dist": 5.0,
        },
        # Pursuit samples are intentionally ignored for boundary correction.
        {
            "phase": "pursuit",
            "x": 0.0,
            "y": 2.0,
            "yaw_deg": 140.0,
            "front_dist": 3.0,
            "rear_dist": 3.0,
            "left_dist": 3.0,
            "right_dist": 3.0,
        },
    ]

    refined = hangar._refine_boundary_from_route_samples(
        boundary,
        samples,
        wall_distance=3.0,
    )

    xs = [point["x"] for point in refined]
    ys = [point["y"] for point in refined]
    assert abs(max(xs) - 6.75) < 0.2
    assert abs(max(ys) - 4.45) < 0.2
    assert abs(min(xs) + 4.3) < 0.2
    assert abs(min(ys) + 3.6) < 0.2


def test_current_landing_targets_use_current_rear_left(mock_lidar_scan):
    targets = hangar._current_landing_targets(
        _lidar(mock_lidar_scan(rear=8.0, left=2.5)),
        fallback_wall_distance=3.0,
    )

    assert abs(targets.rear - 8.0) < 0.5
    assert abs(targets.left - 2.5) < 0.5


@pytest.mark.asyncio
async def test_fly_to_point_safely_blocks_forward_when_front_unsafe(
    mock_lidar_scan,
    monkeypatch,
):
    monkeypatch.setattr(hangar, "RETURN_BLOCKED_TIMEOUT_S", 0.0)
    drone = _drone(positions=[(0.0, 0.0)] * 5, yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=0.5, rear=5.0, left=5.0, right=5.0))

    result = await hangar.fly_to_point_safely(
        drone,
        lidar,
        {"x": 2.0, "y": 0.0},
        label="test-return",
        timeout_s=1.0,
    )

    assert result["ok"] is False
    assert result["reason"] == "blocked"
    sent = [call.args[0] for call in drone.set_velocity.await_args_list if call.args]
    assert sent
    assert all(cmd.forward_m_s <= 0.01 for cmd in sent)


@pytest.mark.asyncio
async def test_record_map_sample_records_all_cardinal_hits(mock_lidar_scan):
    mapper = hangar.MapUnit()
    mapper.start_mapping()
    drone = _drone(positions=[(10.0, 20.0)], yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=4.0, rear=3.0, left=2.0, right=5.0))

    ok = await hangar.record_map_sample(mapper, drone, lidar)

    assert ok is True
    assert len(mapper.points) == 1
    assert len(mapper.wall_points) == 4
    assert {"x": 14.0, "y": 20.0} in mapper.wall_points
    assert {"x": 7.0, "y": 20.0} in mapper.wall_points
    assert {"x": 10.0, "y": 18.0} in mapper.wall_points
    assert {"x": 10.0, "y": 25.0} in mapper.wall_points


@pytest.mark.asyncio
async def test_rotate_to_yaw_stops_within_tolerance():
    drone = _drone(positions=[(0.0, 0.0)], yaw=0.0)

    result = await hangar.rotate_to_yaw(
        drone,
        0.0,
        timeout_s=1.0,
        tolerance_deg=5.0,
    )

    assert result["ok"] is True
    assert result["reason"] == "reached"
    assert drone.set_velocity.await_count >= 3


@pytest.mark.asyncio
async def test_reverse_wall_follow_to_point_commands_negative_forward(mock_lidar_scan):
    drone = _drone(positions=[(1.0, 0.0)] * 5, yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=5.0, rear=5.0, left=2.0, right=5.0))

    await hangar.reverse_wall_follow_to_point(
        drone,
        lidar,
        {"x": 0.0, "y": 0.0},
        wall_distance=2.0,
        timeout_s=0.06,
    )

    sent = [call.args[0] for call in drone.set_velocity.await_args_list if call.args]
    assert any(cmd.forward_m_s < 0.0 for cmd in sent)
