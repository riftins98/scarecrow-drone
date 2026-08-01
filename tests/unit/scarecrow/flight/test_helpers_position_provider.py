"""Takeoff helpers read through the telemetry cache when given one.

These helpers poll every 0.2-0.5s for up to two minutes. Left as one-shots they
open a MAVSDK subscription per sample against a stream Drone already holds a
persistent subscription to, and the two contend: MAVSDK starts logging "User
callback queue slow" and samples arrive late.

They still take a raw mavsdk.System, so the provider has to be optional -- older
scripts and tests call them without a Drone wrapper at all.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scarecrow.flight.helpers import get_position, wait_for_altitude, wait_for_stable


def _sample(down_m=-5.0, vz=0.0):
    return SimpleNamespace(
        position=SimpleNamespace(down_m=down_m, north_m=0.0, east_m=0.0),
        velocity=SimpleNamespace(down_m_s=vz),
    )


def _system_yielding(sample):
    """A mavsdk.System whose telemetry stream yields one sample forever."""

    async def stream():
        while True:
            yield sample

    system = MagicMock()
    system.telemetry.position_velocity_ned = stream
    return system


class TestGetPosition:
    @pytest.mark.asyncio
    async def test_uses_the_provider_when_given(self):
        system = MagicMock()
        system.telemetry.position_velocity_ned = MagicMock(
            side_effect=AssertionError("must not subscribe when a provider exists")
        )
        provider = AsyncMock(return_value=_sample())

        result = await get_position(system, provider)

        provider.assert_awaited_once()
        assert result.position.down_m == -5.0

    @pytest.mark.asyncio
    async def test_falls_back_to_a_subscription_without_a_provider(self):
        """Callers holding only a System must keep working unchanged."""
        result = await get_position(_system_yielding(_sample(down_m=-3.0)))

        assert result.position.down_m == -3.0


class TestWaitForAltitude:
    @pytest.mark.asyncio
    async def test_reaches_target_through_the_provider(self):
        provider = AsyncMock(return_value=_sample(down_m=-5.0))

        ok = await wait_for_altitude(
            MagicMock(), 4.0, ground_z=0.0, timeout=2.0, position_provider=provider
        )

        assert ok is True
        assert provider.await_count >= 1

    @pytest.mark.asyncio
    async def test_never_subscribes_when_a_provider_is_given(self):
        """The whole point: no per-sample subscription during a 2-minute climb."""
        system = MagicMock()
        system.telemetry.position_velocity_ned = MagicMock(
            side_effect=AssertionError("subscribed despite having a provider")
        )

        await wait_for_altitude(
            system,
            4.0,
            ground_z=0.0,
            timeout=1.0,
            position_provider=AsyncMock(return_value=_sample(down_m=-5.0)),
        )

    @pytest.mark.asyncio
    async def test_times_out_when_the_drone_never_climbs(self):
        provider = AsyncMock(return_value=_sample(down_m=0.0))

        ok = await wait_for_altitude(
            MagicMock(), 5.0, ground_z=0.0, timeout=1.0, position_provider=provider
        )

        assert ok is False

    @pytest.mark.asyncio
    async def test_a_none_sample_is_skipped_not_treated_as_ground(self):
        """An empty cache must not read as altitude zero.

        Returning None early in the climb would otherwise look like the drone
        never left the ground, and takeoff would sit there until timeout.
        """
        provider = AsyncMock(side_effect=[None, None, _sample(down_m=-5.0)])

        ok = await wait_for_altitude(
            MagicMock(), 4.0, ground_z=0.0, timeout=3.0, position_provider=provider
        )

        assert ok is True


class TestWaitForStable:
    @pytest.mark.asyncio
    async def test_reports_stable_through_the_provider(self):
        provider = AsyncMock(return_value=_sample(vz=0.0))

        ok = await wait_for_stable(
            MagicMock(),
            ground_z=0.0,
            stable_secs=0.1,
            timeout=2.0,
            position_provider=provider,
        )

        assert ok is True

    @pytest.mark.asyncio
    async def test_a_climbing_drone_is_not_reported_stable(self):
        provider = AsyncMock(return_value=_sample(vz=1.5))

        ok = await wait_for_stable(
            MagicMock(),
            ground_z=0.0,
            stable_secs=0.1,
            timeout=0.6,
            position_provider=provider,
        )

        assert ok is False

    @pytest.mark.asyncio
    async def test_none_samples_do_not_count_toward_stability(self):
        """A silent cache is not evidence of a settled drone."""
        provider = AsyncMock(return_value=None)

        ok = await wait_for_stable(
            MagicMock(),
            ground_z=0.0,
            stable_secs=0.1,
            timeout=0.5,
            position_provider=provider,
        )

        assert ok is False
