"""Async manoeuvres that put the drone in a known corner pose.

`corner_approach.py` and `distance_stabilizer.py` are pure controllers: scan in,
velocity out. They cannot fly anything on their own. These are the loops that
drive them -- read lidar, step the controller, add the altitude term, command
the drone, decide when it is done.

Both hold altitude while they work. That matters: the pure controllers only
produce horizontal velocity, so without the vertical term the drone drifts off
its target AGL during what can be a 45-second manoeuvre, and a mission that
carefully computed a ceiling-safe altitude quietly stops flying at it.
"""
from __future__ import annotations

import asyncio
import math
import time

from scarecrow.controllers.corner_approach import CornerApproachController
from scarecrow.controllers.distance_stabilizer import (
    DistanceStabilizerController,
    DistanceTargets,
)
from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.flight.altitude import agl_from_position, altitude_hold_down_speed
from scarecrow.util.formatting import format_meters

DEFAULT_START_SIDE = "left"

# Start stabilisation: slow and tight. This runs once, before the mission
# proper, and its output is the reference pose everything else is measured
# against -- worth spending time to get right.
START_TIMEOUT_S = 45.0
START_MAX_SPEED_M_S = 0.16
START_TOLERANCE_M = 0.15
START_STABLE_TIME_S = 0.20
START_MIN_CLEARANCE_M = 1.0

# Post-turn stabilisation: faster and looser. Runs after every 90-degree turn,
# and the following wall-follow leg will correct any residual error anyway.
CORNER_TIMEOUT_S = 40.0
CORNER_MAX_SPEED_M_S = 0.30
CORNER_TOLERANCE_M = 0.15
CORNER_STABLE_TIME_S = 1.0

# Consecutive in-band altitude samples required before a manoeuvre may finish.
_ALTITUDE_STABLE_HITS_REQUIRED = 3


async def _current_agl(drone) -> float:
    """AGL now, or +inf if the position read stalls.

    Infinity rather than an exception: a momentarily unavailable position
    should make the altitude term inert (error is infinite, never in band), not
    abort a manoeuvre that is otherwise proceeding safely.
    """
    try:
        pos = await asyncio.wait_for(drone.get_position(), timeout=0.5)
        return agl_from_position(pos, drone.ground_z)
    except Exception:
        return math.inf


async def approach_start_corner(
    drone,
    lidar,
    *,
    wall_distance: float,
    target_alt_m: float,
    start_side: str = DEFAULT_START_SIDE,
    timeout_s: float = START_TIMEOUT_S,
    label: str = "hangar-circuit-start",
) -> str | None:
    """Fly to the rear corner on ``start_side``. Returns the side, or None.

    A left-wall circuit assumes it starts with a wall behind and the followed
    wall on the left. When the operator picks the right-hand rear corner this
    stabilises there and returns "right" so the caller can rotate to normalise
    -- the manoeuvre reports what it achieved rather than deciding the turn.

    None means "unsafe or timed out"; the caller should land.
    """
    first_scan = lidar.get_scan()
    if first_scan is None:
        print(f"  [{label}] ERROR: no lidar scan for start stabilization")
        return None

    side = start_side if start_side in ("left", "right") else DEFAULT_START_SIDE
    print(
        f"  [{label}] selected rear corner is {side}; "
        f"targeting rear={wall_distance:.1f}m {side}={wall_distance:.1f}m"
    )

    controller = CornerApproachController(
        side=side,
        rear_distance=wall_distance,
        side_distance=wall_distance,
        max_forward_speed=START_MAX_SPEED_M_S,
        max_lateral_speed=START_MAX_SPEED_M_S,
        max_total_speed=START_MAX_SPEED_M_S,
        tolerance=START_TOLERANCE_M,
        stable_time=START_STABLE_TIME_S,
        min_clearance=START_MIN_CLEARANCE_M,
    )
    started = time.time()
    step = 0
    altitude_stable_hits = 0

    while time.time() - started < timeout_s:
        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue

        agl = await _current_agl(drone)
        rear = scan.rear_distance()
        side_dist = scan.left_distance() if side == "left" else scan.right_distance()
        result = controller.update(scan)
        down_speed, alt_error, altitude_ok = altitude_hold_down_speed(agl, target_alt_m)
        altitude_stable_hits = altitude_stable_hits + 1 if altitude_ok else 0

        if result.unsafe:
            await drone.set_velocity(VelocityCommand())
            print(
                f"  [{label}] ABORT: unsafe clearance "
                f"rear={rear:.2f}m {side}={side_dist:.2f}m"
            )
            return None

        cmd = result.command
        cmd.down_m_s = down_speed
        await drone.set_velocity(cmd)

        if step % 20 == 0:
            print(
                f"  [{label}] {time.time() - started:.1f}s "
                f"rear={rear:.2f}m {side}={side_dist:.2f}m "
                f"agl={format_meters(agl, 2)} alt_err={alt_error:+.2f}m "
                f"cmd: fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} "
                f"down={cmd.down_m_s:+.2f}"
            )

        # Both conditions, not either: horizontal position and altitude have to
        # be right together, or the mission starts from a pose that is only
        # half correct.
        if result.done and altitude_stable_hits >= _ALTITUDE_STABLE_HITS_REQUIRED:
            await drone.set_velocity(VelocityCommand())
            print(
                f"  [{label}] LOCKED: "
                f"rear={rear:.2f}m {side}={side_dist:.2f}m "
                f"agl={agl:.2f}m target_alt={target_alt_m:.2f}m"
            )
            return side

        step += 1
        await asyncio.sleep(0.05)

    await drone.set_velocity(VelocityCommand())
    scan = lidar.get_scan()
    if scan is not None:
        print(
            f"  [{label}] TIMEOUT: "
            f"rear={scan.rear_distance():.2f}m "
            f"left={scan.left_distance():.2f}m "
            f"right={scan.right_distance():.2f}m"
        )
    return None


async def stabilize_corner(
    drone,
    lidar,
    *,
    wall_distance: float,
    target_alt_m: float,
    timeout_s: float = CORNER_TIMEOUT_S,
) -> bool:
    """Settle rear/left distances and altitude after a 90-degree turn.

    Returns False on timeout. Callers generally warn and continue rather than
    abort -- the next wall-follow leg re-establishes the wall reference anyway,
    so a slightly imperfect corner is recoverable.
    """
    stabilizer = DistanceStabilizerController(
        targets=DistanceTargets(rear=wall_distance, left=wall_distance),
        max_forward_speed=CORNER_MAX_SPEED_M_S,
        max_lateral_speed=CORNER_MAX_SPEED_M_S,
        tolerance=CORNER_TOLERANCE_M,
        stable_time=CORNER_STABLE_TIME_S,
    )
    started = time.time()
    step = 0
    altitude_stable_hits = 0

    while time.time() - started < timeout_s:
        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue

        agl = await _current_agl(drone)
        cmd = stabilizer.update(scan)
        down_speed, alt_error, altitude_ok = altitude_hold_down_speed(agl, target_alt_m)
        altitude_stable_hits = altitude_stable_hits + 1 if altitude_ok else 0
        cmd.down_m_s = down_speed
        await drone.set_velocity(cmd)

        if step % 10 == 0:
            print(
                f"  [corner] front={scan.front_distance():.2f}m "
                f"left={scan.left_distance():.2f}m "
                f"rear={scan.rear_distance():.2f}m "
                f"right={scan.right_distance():.2f}m "
                f"agl={format_meters(agl, 2)} alt_err={alt_error:+.2f}m "
                f"down={cmd.down_m_s:+.2f}"
            )

        if stabilizer.done and altitude_stable_hits >= _ALTITUDE_STABLE_HITS_REQUIRED:
            await drone.set_velocity(VelocityCommand())
            print(
                f"  [corner] LOCKED: left={scan.left_distance():.2f}m "
                f"rear={scan.rear_distance():.2f}m "
                f"agl={agl:.2f}m target_alt={target_alt_m:.2f}m"
            )
            return True

        step += 1
        await asyncio.sleep(0.05)

    await drone.set_velocity(VelocityCommand())
    return False
