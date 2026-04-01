"""Precise 90° rotation controller using compass + lidar SVD alignment.

Handles GPS-denied heading drift by using lidar wall geometry
for fine alignment after a coarse compass turn.

Works for both right and left turns.
"""
from __future__ import annotations

import asyncio
import math

from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed

from ..sensors.lidar.base import LidarSource


def normalize_angle(deg: float) -> float:
    """Normalize angle to -180..180."""
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


async def get_yaw(drone: System) -> float:
    """Get current yaw in degrees (-180 to 180)."""
    async for att in drone.telemetry.attitude_euler():
        return att.yaw_deg


async def rotate_90(
    drone: System,
    lidar: LidarSource,
    direction: str = "right",
    compass_overshoot: float = 95.0,
    compass_speed: float = 30.0,
    compass_tolerance: float = 3.0,
    svd_tolerance: float = 2.0,
    svd_gain: float = 3.0,
    svd_max_speed: float = 15.0,
    svd_timeout: int = 200,
) -> bool:
    """Rotate exactly 90° using compass for coarse turn + lidar SVD for precision.

    Step 1: Compass coarse turn — fast rotation to ~95° (overshoots to
            compensate for GPS-denied heading drift).
    Step 2: Lidar SVD alignment — fine-tune heading until the left wall
            is exactly perpendicular (wall direction parallel to forward).

    Args:
        drone: MAVSDK System (must be in offboard mode).
        lidar: Active LidarSource providing scans.
        direction: "right" or "left".
        compass_overshoot: Compass target angle (slightly over 90° to
            compensate for drift). Default 95°.
        compass_speed: Max turn speed in deg/s. Default 30.
        compass_tolerance: Compass phase done when within this many degrees.
        svd_tolerance: SVD alignment done when wall error < this (degrees).
        svd_gain: Proportional gain for SVD yaw correction.
        svd_max_speed: Max yaw speed during SVD alignment (deg/s).
        svd_timeout: Max iterations for SVD phase (~0.05s each).

    Returns:
        True if alignment succeeded, False if SVD timed out.
    """
    sign = 1 if direction == "right" else -1

    pre_scan = lidar.get_scan()
    if pre_scan:
        print(f"  Pre-turn: front={pre_scan.front_distance():.1f}m left={pre_scan.left_distance():.1f}m")
        err = pre_scan.left_wall_angle_error()
        if err is not None:
            print(f"  Wall alignment error: {math.degrees(err):.1f}°")

    # --- Step 1: Compass coarse turn ---
    start_yaw = await get_yaw(drone)
    target_yaw = normalize_angle(start_yaw + sign * compass_overshoot)
    print(f"  Step 1 (compass): {start_yaw:.0f}° → {target_yaw:.0f}°")

    for _ in range(300):
        current_yaw = await get_yaw(drone)
        error = normalize_angle(target_yaw - current_yaw)

        if abs(error) < compass_tolerance:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
            )
            await asyncio.sleep(0.5)
            print(f"  Step 1 done: {current_yaw:.0f}°")
            break

        speed = min(compass_speed, max(5.0, abs(error) * 1.5))
        yaw_cmd = speed if error > 0 else -speed
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0.0, 0.0, 0.0, yaw_cmd)
        )
        await asyncio.sleep(0.05)

    # --- Step 2: SVD wall alignment ---
    # After turning right, the old front wall is now on the left → align to left
    # After turning left, the old front wall is now on the right → align to right
    align_side = "left" if direction == "right" else "right"
    print(f"  Step 2 (lidar SVD): aligning perpendicular to {align_side} wall...")

    for attempt in range(svd_timeout):
        scan = lidar.get_scan()
        if scan is None:
            await asyncio.sleep(0.05)
            continue

        if align_side == "left":
            wall_error_rad = scan.left_wall_angle_error()
        else:
            wall_error_rad = scan.right_wall_angle_error()

        if wall_error_rad is None:
            await asyncio.sleep(0.05)
            continue

        wall_error_deg = math.degrees(wall_error_rad)

        if abs(wall_error_deg) < svd_tolerance:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
            )
            await asyncio.sleep(0.5)
            final_scan = lidar.get_scan()
            if final_scan:
                wall_dist = final_scan.left_distance() if align_side == "left" else final_scan.right_distance()
                print(f"  Step 2 done: wall error={wall_error_deg:.1f}° "
                      f"front={final_scan.front_distance():.1f}m "
                      f"{align_side}={wall_dist:.1f}m")
            return True

        yaw_cmd = max(-svd_max_speed, min(svd_max_speed, -wall_error_deg * svd_gain))
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(0.0, 0.0, 0.0, yaw_cmd)
        )

        if attempt % 20 == 0:
            print(f"  Aligning... wall error={wall_error_deg:.1f}° left={scan.left_distance():.1f}m")

        await asyncio.sleep(0.05)

    # Timeout
    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )
    print("  SVD alignment timeout")
    return False
