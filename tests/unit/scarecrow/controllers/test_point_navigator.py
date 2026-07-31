"""Point navigation with lidar veto.

Moved from tests/unit/scripts/flight/ when these manoeuvres left the hangar
flight script for scarecrow.controllers.point_navigator.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scarecrow.controllers import point_navigator
from scarecrow.controllers.point_navigator import (
    fly_to_point,
    reverse_wall_follow_to_point,
)


def _position(north, east, down=-2.5):
    return SimpleNamespace(
        position=SimpleNamespace(north_m=north, east_m=east, down_m=down)
    )


def _drone(*, positions, yaw=0.0):
    drone = MagicMock()
    drone.get_position = AsyncMock(side_effect=[_position(*pos) for pos in positions])
    drone.get_yaw = AsyncMock(return_value=yaw)
    drone.set_velocity = AsyncMock()
    drone.ground_z = 0.0
    return drone


def _lidar(scan):
    lidar = MagicMock()
    lidar.get_scan = MagicMock(return_value=scan)
    return lidar


@pytest.mark.asyncio
async def test_fly_to_point_blocks_forward_when_front_unsafe(mock_lidar_scan):
    """The lidar veto must override the position controller, not blend with it."""
    drone = _drone(positions=[(0.0, 0.0)] * 5, yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=0.5, rear=5.0, left=5.0, right=5.0))

    result = await fly_to_point(
        drone,
        lidar,
        {"x": 2.0, "y": 0.0},
        label="test-return",
        timeout_s=1.0,
        blocked_timeout_s=0.0,
    )

    assert result["ok"] is False
    assert result["reason"] == "blocked"
    sent = [call.args[0] for call in drone.set_velocity.await_args_list if call.args]
    assert sent
    assert all(cmd.forward_m_s <= 0.01 for cmd in sent)


@pytest.mark.asyncio
async def test_fly_to_point_refuses_to_move_without_a_scan():
    """No scan means no veto is possible, so nothing may move."""
    drone = _drone(positions=[(0.0, 0.0)] * 5, yaw=0.0)

    result = await fly_to_point(
        drone,
        _lidar(None),
        {"x": 2.0, "y": 0.0},
        label="test-noscan",
        timeout_s=1.0,
        blocked_timeout_s=0.0,
    )

    assert result["ok"] is False
    assert result["reason"] == "blocked"
    sent = [call.args[0] for call in drone.set_velocity.await_args_list if call.args]
    assert all(
        cmd.forward_m_s == 0.0 and cmd.right_m_s == 0.0 for cmd in sent
    )


@pytest.mark.asyncio
async def test_fly_to_point_reports_reached_when_stable(mock_lidar_scan):
    drone = _drone(positions=[(0.0, 0.0)] * 20, yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=5.0, rear=5.0, left=5.0, right=5.0))

    result = await fly_to_point(
        drone,
        lidar,
        {"x": 0.0, "y": 0.0},
        label="test-reached",
        timeout_s=2.0,
        stable_time_s=0.0,
    )

    assert result["ok"] is True
    assert result["reason"] == "reached"


@pytest.mark.asyncio
async def test_reverse_wall_follow_commands_negative_forward(mock_lidar_scan):
    drone = _drone(positions=[(1.0, 0.0)] * 5, yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=5.0, rear=5.0, left=2.0, right=5.0))

    await reverse_wall_follow_to_point(
        drone,
        lidar,
        {"x": 0.0, "y": 0.0},
        wall_distance=2.0,
        timeout_s=0.06,
    )

    sent = [call.args[0] for call in drone.set_velocity.await_args_list if call.args]
    assert any(cmd.forward_m_s < 0.0 for cmd in sent)


@pytest.mark.asyncio
async def test_reverse_wall_follow_aborts_on_unsafe_rear(mock_lidar_scan):
    """Reversing is the one case where the rear wall is the danger."""
    drone = _drone(positions=[(1.0, 0.0)] * 5, yaw=0.0)
    lidar = _lidar(mock_lidar_scan(front=5.0, rear=0.3, left=2.0, right=5.0))

    ok = await reverse_wall_follow_to_point(
        drone,
        lidar,
        {"x": 0.0, "y": 0.0},
        wall_distance=2.0,
        timeout_s=1.0,
    )

    assert ok is False
