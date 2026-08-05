"""Corner stabilisation holds still before correcting position.

The phase runs immediately after a 90-degree rotation, which is the worst
moment to trust the estimator: rotational flow contaminates optical flow's
translational estimate. Measured across a corner, the drone's reported
body-frame velocity disagreed with what the lidar actually saw by up to
0.30 m/s, decaying to zero by roughly t+7s. Correcting position during that
window means flying to numbers that are wrong, then unwinding it.

Flight-measured, four corners per run:

    settle    corner time    mission
    0.0s      81.5s          6m02s / 6m17s
    2.0s      58.1s          5m47.6s
    3.0s      44.5s          5m21.8s     <- chosen
    3.0s      44.9s          5m24.9s     <- repeat, reproduces
    4.0s      75.3s          5m47.6s

Longer is not better: with no position control during the hold the drone
drifts, so an over-long settle starts the correction from further away.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from scarecrow.controllers import corner_stabilizer
from scarecrow.controllers.corner_stabilizer import CORNER_SETTLE_S, stabilize_corner
from scarecrow.sensors.lidar.base import LidarScan


def _scan(rear=2.0, left=2.0):
    ranges = np.full(1440, 12.0, dtype=np.float32)
    ranges[:30] = rear
    ranges[1410:] = rear
    ranges[1040:1100] = left
    return LidarScan(ranges=ranges, angle_min=-np.pi, angle_max=np.pi)


def _drone():
    drone = MagicMock()
    drone.ground_z = 0.0
    pos = MagicMock()
    pos.position.down_m = -5.0
    drone.get_position = AsyncMock(return_value=pos)
    drone.set_velocity = AsyncMock()
    return drone


def _lidar(scan=None):
    lidar = MagicMock()
    lidar.get_scan = MagicMock(return_value=scan if scan is not None else _scan())
    return lidar


class TestSettleHold:
    @pytest.mark.asyncio
    async def test_no_horizontal_command_during_the_settle(self):
        """The whole point: do not fly on an estimate that is still recovering."""
        drone, lidar = _drone(), _lidar()

        await stabilize_corner(
            drone, lidar, wall_distance=2.0, target_alt_m=5.0,
            timeout_s=0.01, settle_s=0.3,
        )

        during = drone.set_velocity.await_args_list
        assert during, "expected velocity commands during the settle"
        # Every command issued before the timeout must be vertical only.
        assert all(
            c.args[0].forward_m_s == 0.0 and c.args[0].right_m_s == 0.0
            for c in during[:3]
        ), "settle issued a horizontal correction"

    @pytest.mark.asyncio
    async def test_altitude_still_holds_while_settling(self):
        """Altitude uses the rangefinder, not optical flow, so it stays live.

        Drifting off a ceiling-safe altitude while waiting would trade one
        problem for a worse one.
        """
        drone, lidar = _drone(), _lidar()
        drone.get_position.return_value.position.down_m = -3.0   # 2m below target

        await stabilize_corner(
            drone, lidar, wall_distance=2.0, target_alt_m=5.0,
            timeout_s=0.01, settle_s=0.3,
        )

        assert any(c.args[0].down_m_s != 0.0 for c in drone.set_velocity.await_args_list)

    @pytest.mark.asyncio
    async def test_the_settle_actually_takes_time(self):
        loop = asyncio.get_event_loop()
        drone, lidar = _drone(), _lidar()

        start = loop.time()
        await stabilize_corner(
            drone, lidar, wall_distance=2.0, target_alt_m=5.0,
            timeout_s=0.01, settle_s=0.3,
        )

        assert loop.time() - start >= 0.3

    @pytest.mark.asyncio
    async def test_settle_can_be_disabled(self):
        """Callers that know the estimate is good should not have to pay for it."""
        loop = asyncio.get_event_loop()
        drone, lidar = _drone(), _lidar()

        start = loop.time()
        await stabilize_corner(
            drone, lidar, wall_distance=2.0, target_alt_m=5.0,
            timeout_s=0.01, settle_s=0.0,
        )

        assert loop.time() - start < 0.25

    @pytest.mark.asyncio
    async def test_a_missing_scan_during_settle_is_survivable(self):
        drone, lidar = _drone(), _lidar()
        lidar.get_scan = MagicMock(return_value=None)

        result = await stabilize_corner(
            drone, lidar, wall_distance=2.0, target_alt_m=5.0,
            timeout_s=0.01, settle_s=0.2,
        )

        assert result is False


class TestChosenValue:
    def test_settle_is_the_flight_measured_value(self):
        """2.0s left the transient unabsorbed; 4.0s drifted. Both measured."""
        assert CORNER_SETTLE_S == pytest.approx(3.0)

    def test_settle_is_shorter_than_the_stabilisation_timeout(self):
        """A settle longer than the budget would leave no time to correct."""
        assert CORNER_SETTLE_S < corner_stabilizer.CORNER_TIMEOUT_S
