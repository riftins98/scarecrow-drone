"""Common async flight helpers for MAVSDK-based scripts."""
from __future__ import annotations

import asyncio
import time


async def get_position(drone):
    """Read current NED position + velocity (one-shot)."""
    async for pos in drone.telemetry.position_velocity_ned():
        return pos


async def wait_for_altitude(drone, target_alt: float, ground_z: float, timeout: float = 30) -> bool:
    """Wait until drone reaches target altitude AGL.

    Args:
        drone: MAVSDK System instance.
        target_alt: Target altitude in meters above ground.
        ground_z: Ground reference down_m (NED).
        timeout: Maximum wait in seconds.

    Returns:
        True if altitude reached, False on timeout.
    """
    for i in range(int(timeout / 0.5)):
        await asyncio.sleep(0.5)
        async for pos in drone.telemetry.position_velocity_ned():
            agl = -(pos.position.down_m - ground_z)
            print(f"  Climbing... {agl:.1f}m / {target_alt}m")
            if agl >= target_alt - 0.3:
                return True
            break
    return False


async def wait_for_stable(
    drone,
    ground_z: float,
    tolerance: float = 0.15,
    stable_secs: float = 2.0,
    timeout: float = 15.0,
) -> bool:
    """Wait until vertical velocity is stable for consecutive seconds.

    Args:
        drone: MAVSDK System instance.
        ground_z: Ground reference down_m (NED).
        tolerance: Maximum abs(vz) to count as stable.
        stable_secs: How long vz must stay within tolerance.
        timeout: Maximum wait in seconds.

    Returns:
        True if stable, False on timeout.
    """
    stable_since = None
    deadline = time.time() + timeout

    while time.time() < deadline:
        async for pos in drone.telemetry.position_velocity_ned():
            agl = -(pos.position.down_m - ground_z)
            vz = abs(pos.velocity.down_m_s)
            break

        if vz < tolerance:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_secs:
                print(f"  Stable at {agl:.2f}m (vz={vz:.3f} m/s)")
                return True
        else:
            stable_since = None

        await asyncio.sleep(0.2)

    print(f"  Stability timeout — continuing")
    return False


async def log_position(drone, phase: str, ground_z: float) -> None:
    """Pretty-print current position telemetry."""
    pos = await get_position(drone)
    agl = -(pos.position.down_m - ground_z)
    vz = pos.velocity.down_m_s
    n = pos.position.north_m
    e = pos.position.east_m
    print(f"  [{phase:12s}] agl={agl:6.3f}m  vz={vz:+.3f}  n={n:+.3f} e={e:+.3f}")
