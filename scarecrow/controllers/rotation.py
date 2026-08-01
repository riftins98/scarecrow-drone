"""Precise 90° rotation controller using compass + lidar SVD alignment.

Handles GPS-denied heading drift by using lidar wall geometry
for fine alignment after a coarse compass turn.

Works for both right and left turns.
"""
from __future__ import annotations

import asyncio
import math
import time

from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed

from ..sensors.lidar.base import LidarSource

# Imported, not redefined. This module used to carry a byte-identical copy of
# normalize_angle -- exactly the drift scarecrow.util exists to prevent. The
# import keeps `from .rotation import normalize_angle` working for existing
# callers while there is only one definition.
from ..util.math_utils import normalize_angle  # noqa: F401


async def get_yaw(drone: System) -> float:
    """Get current yaw in degrees (-180 to 180).

    Opens a fresh subscription per call. rotate_90 polls yaw hundreds of times
    per turn, so it should be given a cached provider instead -- see the
    `yaw_provider` argument. This remains for callers holding only a System.
    """
    async for att in drone.telemetry.attitude_euler():
        return att.yaw_deg


async def rotate_90(
    drone: System,
    lidar: LidarSource,
    direction: str = "right",
    yaw_provider=None,
    compass_overshoot: float = 95.0,
    compass_speed: float = 30.0,
    compass_tolerance: float = 3.0,
    svd_tolerance: float = 2.0,
    svd_gain: float = 3.0,
    svd_max_speed: float = 15.0,
    svd_timeout_s: float = 25.0,
    svd_timeout: int | None = None,
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
        svd_timeout_s: Wall-clock budget for the SVD phase.

            Was `svd_timeout: int = 200` iterations at 0.05s -- 10s of wall
            clock, but the drone rotates in SIMULATED time. At the RTF measured
            during flight (median 0.134) those 10s bought only ~1.3s of sim
            time, nowhere near enough to correct a large error at the 15 deg/s
            cap: an alignment was observed timing out while still converging,
            at 11.6 degrees and closing. Seconds also keep the budget honest on
            hardware, where RTF is 1.0 by definition.

            The iteration form is still accepted and converted.

        yaw_provider: Optional async callable returning the current yaw. Pass
            `Drone.get_yaw` so the compass phase reads a cached value instead
            of opening a subscription per poll.

            This matters more than it looks. The compass phase polls yaw up to
            300 times at 0.05s, and each default poll opens a new
            attitude_euler subscription. Once Drone began holding a persistent
            subscription of its own, the two contended: MAVSDK logged "User
            callback queue slow" 43 times in one flight (against 2 before) and
            three of four corner turns failed their SVD alignment. Sharing one
            stream removes the contention.

    Returns:
        True if alignment succeeded, False if SVD timed out.
    """
    read_yaw = yaw_provider or (lambda: get_yaw(drone))
    if svd_timeout is not None:
        svd_timeout_s = max(1, svd_timeout) * 0.05
    sign = 1 if direction == "right" else -1

    pre_scan = lidar.get_scan()
    if pre_scan:
        print(f"  Pre-turn: front={pre_scan.front_distance():.1f}m left={pre_scan.left_distance():.1f}m")
        err = pre_scan.left_wall_angle_error()
        if err is not None:
            print(f"  Wall alignment error: {math.degrees(err):.1f}°")

    # --- Step 1: Compass coarse turn ---
    start_yaw = await read_yaw()
    target_yaw = normalize_angle(start_yaw + sign * compass_overshoot)
    print(f"  Step 1 (compass): {start_yaw:.0f}° → {target_yaw:.0f}°")

    for _ in range(300):
        current_yaw = await read_yaw()
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

    svd_deadline = time.monotonic() + svd_timeout_s
    attempt = 0
    while time.monotonic() < svd_deadline:
        attempt += 1
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


# ---------------------------------------------------------------------------
# Absolute yaw hold
# ---------------------------------------------------------------------------
# rotate_90() above turns by a *relative* amount and refines against wall
# geometry. This one drives to an *absolute* PX4 yaw and is what a mission uses
# to put a heading back exactly where it was -- after a pursuit, or after the
# entry planner rotated away from the wall-follow heading.
#
# It works on the Drone wrapper rather than a raw System because callers are
# already in offboard mode holding a Drone, and it deliberately does not
# consult lidar: the point is to restore a remembered heading, which may not
# correspond to any wall the drone can currently see.

ROTATE_TO_YAW_SPEED_DEG_S = 12.0
ROTATE_TO_YAW_TOLERANCE_DEG = 5.0
ROTATE_TO_YAW_TIMEOUT_S = 25.0

# PX4 ignores very small yaw rates, so a drone a few degrees off would creep
# forever. Below this the command is bumped to the floor value instead.
_MIN_EFFECTIVE_YAW_RATE_DEG_S = 3.0

# Consecutive in-tolerance samples required. One is not enough: yaw estimate
# noise alone can put a single sample inside the band mid-rotation.
_STABLE_HITS_REQUIRED = 3


async def rotate_to_yaw(
    drone,
    target_yaw_deg: float,
    *,
    timeout_s: float = ROTATE_TO_YAW_TIMEOUT_S,
    tolerance_deg: float = ROTATE_TO_YAW_TOLERANCE_DEG,
    max_speed_deg_s: float = ROTATE_TO_YAW_SPEED_DEG_S,
) -> dict:
    """Rotate in place until PX4 yaw matches ``target_yaw_deg``.

    Returns a result dict (``ok``, ``reason``, final and target yaw, error,
    elapsed) rather than a bool -- missions record the yaw error in the mission
    map, and "restored to within 4 degrees" is worth keeping.
    """
    from .wall_follow import VelocityCommand

    started = time.time()
    stable_hits = 0
    final_yaw = math.nan
    final_error = math.inf

    while time.time() - started < timeout_s:
        current_yaw = await drone.get_yaw()
        error = normalize_angle(target_yaw_deg - current_yaw)
        final_yaw = current_yaw
        final_error = error

        if abs(error) <= tolerance_deg:
            stable_hits += 1
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.15)
            if stable_hits >= _STABLE_HITS_REQUIRED:
                print(
                    f"  [heading] restored yaw={current_yaw:.1f} "
                    f"target={target_yaw_deg:.1f} err={error:+.1f}deg"
                )
                return {
                    "ok": True,
                    "reason": "reached",
                    "yaw_deg": current_yaw,
                    "target_yaw_deg": target_yaw_deg,
                    "yaw_error_deg": error,
                    "elapsed_s": time.time() - started,
                }
            continue

        stable_hits = 0
        yaw_cmd = max(-max_speed_deg_s, min(max_speed_deg_s, error * 0.8))
        if abs(yaw_cmd) < _MIN_EFFECTIVE_YAW_RATE_DEG_S:
            yaw_cmd = (
                _MIN_EFFECTIVE_YAW_RATE_DEG_S
                if yaw_cmd >= 0
                else -_MIN_EFFECTIVE_YAW_RATE_DEG_S
            )
        await drone.set_velocity(VelocityCommand(yawspeed_deg_s=yaw_cmd))
        await asyncio.sleep(0.08)

    await drone.set_velocity(VelocityCommand())
    print(
        f"  [heading] timeout yaw={final_yaw:.1f} "
        f"target={target_yaw_deg:.1f} err={final_error:+.1f}deg"
    )
    return {
        "ok": False,
        "reason": "timeout",
        "yaw_deg": final_yaw,
        "target_yaw_deg": target_yaw_deg,
        "yaw_error_deg": final_error,
        "elapsed_s": time.time() - started,
    }


async def rotate_relative_90(drone, lidar, degrees: float) -> bool:
    """Turn exactly +/-90 degrees using compass + lidar SVD alignment.

    Thin adapter so missions holding a Drone wrapper can reach rotate_90(),
    which takes a raw MAVSDK System. Rejects any other angle rather than
    silently rounding: rotate_90's wall-alignment step assumes a quarter turn.
    """
    if not math.isclose(abs(degrees), 90.0, abs_tol=1e-6):
        raise ValueError("package rotation wrapper only supports +/-90 degrees")
    direction = "right" if degrees > 0.0 else "left"
    # Hand rotate_90 the cached yaw so its compass poll does not open a new
    # subscription per iteration alongside Drone's persistent one.
    return await rotate_90(
        drone.system, lidar, direction=direction, yaw_provider=drone.get_yaw
    )
