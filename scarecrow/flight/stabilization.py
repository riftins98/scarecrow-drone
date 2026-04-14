"""Lidar-based position stabilization for offboard flight."""
from __future__ import annotations

import asyncio
import time

from mavsdk.offboard import VelocityBodyYawspeed

from ..controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from ..sensors.lidar.base import LidarSource


async def lidar_stabilize(
    drone,
    lidar: LidarSource,
    targets: DistanceTargets,
    label: str = "stabilize",
    timeout: float = 12.0,
) -> bool:
    """Hold position using lidar wall distances until stable.

    Wraps DistanceStabilizerController with async offboard commands,
    timeout handling, and diagnostic logging.

    Args:
        drone: MAVSDK System instance (must already be in offboard mode).
        lidar: Active LidarSource providing scans.
        targets: Wall-distance targets to stabilize at.
        label: Label for log messages (e.g. "pre-hover", "pre-land").
        timeout: Maximum stabilization time in seconds.

    Returns:
        True if stabilized, False on timeout.
    """
    stabilizer = DistanceStabilizerController(
        targets=targets,
        kp_front_rear=0.40,
        kp_left_right=0.45,
        max_forward_speed=0.25,
        max_lateral_speed=0.25,
        tolerance=0.15,
        stable_time=1.5,
    )

    # Log initial state vs targets
    scan = lidar.get_scan()
    if scan:
        _log_distances(scan, targets, label, "Start")

    start = time.time()
    step = 0
    while time.time() - start < timeout:
        scan = lidar.get_scan()
        if scan is None:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.05)
            continue

        cmd = stabilizer.update(scan)
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, 0.0, 0.0)
        )

        step += 1
        if step % 20 == 0:  # log every ~1s
            _log_cmd(scan, targets, label, time.time() - start, cmd)

        if stabilizer.done:
            _log_distances(scan, targets, label, "LOCKED")
            print(f"  [{label}] ({time.time() - start:.1f}s)")
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
            await asyncio.sleep(0.5)
            return True

        await asyncio.sleep(0.05)

    # Timeout
    scan = lidar.get_scan()
    if scan:
        _log_distances(scan, targets, label, "TIMEOUT")
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
    await asyncio.sleep(0.5)
    return False


def _target_axes(targets: DistanceTargets) -> list[tuple[str, float | None]]:
    """Return (name, target_value) pairs for non-None targets."""
    return [
        (name, val) for name, val in [
            ("front", targets.front),
            ("rear", targets.rear),
            ("left", targets.left),
            ("right", targets.right),
        ] if val is not None
    ]


def _log_distances(scan, targets: DistanceTargets, label: str, prefix: str) -> None:
    """Log current distances vs targets."""
    parts = []
    for name, target in _target_axes(targets):
        dist = getattr(scan, f"{name}_distance")()
        parts.append(f"{name}={dist:.2f}m (target {target}m, err={dist - target:+.2f}m)")
    print(f"  [{label}] {prefix}:  {'  '.join(parts)}")


def _log_cmd(scan, targets: DistanceTargets, label: str, elapsed: float, cmd) -> None:
    """Log periodic stabilization status."""
    parts = []
    for name, target in _target_axes(targets):
        dist = getattr(scan, f"{name}_distance")()
        parts.append(f"{name}={dist:.2f}m (err={dist - target:+.2f})")
    print(f"  [{label}] {elapsed:.1f}s  {'  '.join(parts)}  "
          f"cmd: fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f}")
