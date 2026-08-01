"""Absolute yaw hold and the 90-degree rotation adapter.

Moved from tests/unit/scripts/flight/ when these left the hangar flight script
for scarecrow.controllers.rotation.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scarecrow.controllers import rotation
from scarecrow.controllers.rotation import rotate_relative_90, rotate_to_yaw


def _drone(yaw=0.0):
    drone = MagicMock()
    drone.get_yaw = AsyncMock(return_value=yaw)
    drone.set_velocity = AsyncMock()
    return drone


@pytest.mark.asyncio
async def test_rotate_to_yaw_stops_within_tolerance():
    drone = _drone(yaw=0.0)

    result = await rotate_to_yaw(drone, 0.0, timeout_s=1.0, tolerance_deg=5.0)

    assert result["ok"] is True
    assert result["reason"] == "reached"
    # Requires consecutive in-band samples, not just one.
    assert drone.set_velocity.await_count >= 3


@pytest.mark.asyncio
async def test_rotate_to_yaw_times_out_when_yaw_never_moves():
    """A drone that cannot turn must report timeout, not spin forever."""
    drone = _drone(yaw=0.0)

    result = await rotate_to_yaw(drone, 90.0, timeout_s=0.3, tolerance_deg=5.0)

    assert result["ok"] is False
    assert result["reason"] == "timeout"


@pytest.mark.asyncio
async def test_rotate_to_yaw_takes_the_short_way_round():
    """Yaw error must wrap: +179 -> -179 is 2 degrees, not 358.

    Without wrapping this reports a 358-degree error and the drone rotates
    almost the whole way round to reach a heading two degrees away.

    The timeout must clear 3 x 0.15s of stable-sample settling, or the call
    reports timeout even though the yaw was correct the whole time.
    """
    drone = _drone(yaw=179.0)

    result = await rotate_to_yaw(drone, -179.0, timeout_s=1.0, tolerance_deg=5.0)

    assert result["ok"] is True
    assert abs(result["yaw_error_deg"]) <= 5.0


@pytest.mark.asyncio
async def test_rotate_relative_90_delegates_to_package_rotation(monkeypatch):
    drone = _drone()
    lidar = MagicMock()
    rotate = AsyncMock(return_value=True)
    monkeypatch.setattr(rotation, "rotate_90", rotate)

    ok = await rotate_relative_90(drone, lidar, 90.0)

    assert ok is True
    rotate.assert_awaited_once_with(
        drone.system, lidar, direction="right", yaw_provider=drone.get_yaw
    )


@pytest.mark.asyncio
async def test_rotate_relative_90_shares_the_cached_yaw_stream(monkeypatch):
    """rotate_90 must not open its own attitude subscription per poll.

    Its compass phase polls yaw up to 300 times. Once Drone held a persistent
    attitude subscription, that contended with it: MAVSDK logged "User callback
    queue slow" 43 times in one flight (2 before) and 3 of 4 corner turns
    failed SVD alignment. Passing the cached getter is what removes it.
    """
    drone = _drone()
    rotate = AsyncMock(return_value=True)
    monkeypatch.setattr(rotation, "rotate_90", rotate)

    await rotate_relative_90(drone, MagicMock(), 90.0)

    assert rotate.await_args.kwargs["yaw_provider"] is drone.get_yaw


@pytest.mark.asyncio
async def test_rotate_relative_90_rejects_other_angles():
    """rotate_90's wall-alignment step assumes a quarter turn."""
    with pytest.raises(ValueError):
        await rotate_relative_90(_drone(), MagicMock(), 45.0)
