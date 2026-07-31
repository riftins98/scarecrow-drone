"""Driving to a world-frame point, with lidar acting as a hard gate.

Both manoeuvres here exist because the mission needs to *go back* somewhere:
to the pose where a pursuit started, or to the start of an interrupted leg.
Neither is hangar-specific.

The shared idea is that the position controller proposes a velocity and the
lidar may veto it. The controller alone has no idea a wall is there -- it only
knows the target is north-east of here -- so without the veto it will happily
drive into one while reporting healthy progress toward the goal.
"""
from __future__ import annotations

import asyncio
import math
import time

from scarecrow.controllers.wall_follow import VelocityCommand, WallFollowController
from scarecrow.util.math_utils import clamp

DEFAULT_MAX_SPEED_M_S = 0.25
DEFAULT_KP = 0.35
DEFAULT_TOLERANCE_M = 0.35
DEFAULT_STABLE_TIME_S = 1.0
DEFAULT_TIMEOUT_S = 60.0

# How long the lidar may hold every axis at zero before the move is declared
# blocked. Short enough to react, long enough to ride out a single bad scan.
DEFAULT_BLOCKED_TIMEOUT_S = 5.0

DEFAULT_FRONT_CLEARANCE_M = 1.0
DEFAULT_REAR_CLEARANCE_M = 1.0
DEFAULT_SIDE_CLEARANCE_M = 0.8

# Reverse wall-follow: negative forward speed, so the drone backs along the
# wall it is already tracking rather than turning round. Turning would lose the
# wall reference and the heading the caller wants preserved.
DEFAULT_REVERSE_SPEED_M_S = -0.20
DEFAULT_REVERSE_TIMEOUT_S = 90.0


async def fly_to_point(
    drone,
    lidar,
    target: dict,
    *,
    label: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
    stable_time_s: float = DEFAULT_STABLE_TIME_S,
    max_speed_m_s: float = DEFAULT_MAX_SPEED_M_S,
    kp: float = DEFAULT_KP,
    blocked_timeout_s: float = DEFAULT_BLOCKED_TIMEOUT_S,
    front_clearance_m: float = DEFAULT_FRONT_CLEARANCE_M,
    rear_clearance_m: float = DEFAULT_REAR_CLEARANCE_M,
    side_clearance_m: float = DEFAULT_SIDE_CLEARANCE_M,
) -> dict:
    """Fly to a world N/E point using lidar-gated body-frame velocity.

    Returns a result dict with ``ok``/``reason`` (reached, blocked, timeout)
    plus the final pose, rather than a bare bool: callers record all of it in
    the mission map, and "we stopped 0.4m short" is a materially different
    outcome from "we never moved".

    Requires the drone to already be in offboard mode.
    """
    started = time.time()
    stable_since: float | None = None
    blocked_since: float | None = None
    tick = 0
    last_err = math.inf
    last_x = math.nan
    last_y = math.nan
    last_yaw = math.nan

    while time.time() - started < timeout_s:
        pos = await drone.get_position()
        current_yaw = await drone.get_yaw()
        n_err = float(target["x"]) - pos.position.north_m
        e_err = float(target["y"]) - pos.position.east_m
        dist = math.hypot(n_err, e_err)
        last_err = dist
        last_x = pos.position.north_m
        last_y = pos.position.east_m
        last_yaw = current_yaw

        # Require the drone to *hold* the target, not just touch it: optical
        # flow drift can carry it through the tolerance ball in one tick.
        if dist <= tolerance_m:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_time_s:
                await drone.set_velocity(VelocityCommand())
                print(
                    f"  [{label}] reached target "
                    f"(err={dist:.2f}m x={last_x:.2f} y={last_y:.2f} yaw={last_yaw:.1f})"
                )
                return {
                    "ok": True,
                    "reason": "reached",
                    "error_m": dist,
                    "x": last_x,
                    "y": last_y,
                    "yaw_deg": last_yaw,
                    "elapsed_s": time.time() - started,
                }
        else:
            stable_since = None

        # World-frame error -> body frame. The drone keeps its heading and
        # translates; rotating would break the wall reference the caller relies
        # on after the move.
        yaw_rad = math.radians(current_yaw)
        fwd_error = n_err * math.cos(yaw_rad) + e_err * math.sin(yaw_rad)
        right_error = -n_err * math.sin(yaw_rad) + e_err * math.cos(yaw_rad)
        fwd = clamp(kp * fwd_error, -max_speed_m_s, max_speed_m_s)
        right = clamp(kp * right_error, -max_speed_m_s, max_speed_m_s)

        scan = lidar.get_scan()
        if scan is None:
            # No scan means no veto is possible, so refuse to move at all.
            blocked = True
            fwd = 0.0
            right = 0.0
        else:
            if fwd > 0.0 and scan.front_distance() < front_clearance_m:
                fwd = 0.0
            elif fwd < 0.0 and scan.rear_distance() < rear_clearance_m:
                fwd = 0.0

            if right > 0.0 and scan.right_distance() < side_clearance_m:
                right = 0.0
            elif right < 0.0 and scan.left_distance() < side_clearance_m:
                right = 0.0

            blocked = abs(fwd) < 0.01 and abs(right) < 0.01 and dist > tolerance_m

        if blocked:
            if blocked_since is None:
                blocked_since = time.time()
            elif time.time() - blocked_since >= blocked_timeout_s:
                await drone.set_velocity(VelocityCommand())
                print(f"  [{label}] blocked by lidar for {blocked_timeout_s:.1f}s")
                return {
                    "ok": False,
                    "reason": "blocked",
                    "error_m": last_err,
                    "x": last_x,
                    "y": last_y,
                    "yaw_deg": last_yaw,
                    "elapsed_s": time.time() - started,
                }
        else:
            blocked_since = None

        await drone.set_velocity(VelocityCommand(forward_m_s=fwd, right_m_s=right))
        tick += 1
        if tick % 10 == 0:
            print(f"  [{label}] err={dist:.2f}m fwd={fwd:+.2f} right={right:+.2f}")
        await asyncio.sleep(0.1)

    await drone.set_velocity(VelocityCommand())
    print(f"  [{label}] timeout before reaching target (err={last_err:.2f}m)")
    return {
        "ok": False,
        "reason": "timeout",
        "error_m": last_err,
        "x": last_x,
        "y": last_y,
        "yaw_deg": last_yaw,
        "elapsed_s": time.time() - started,
    }


async def reverse_wall_follow_to_point(
    drone,
    lidar,
    target: dict,
    *,
    wall_distance: float,
    side: str = "left",
    timeout_s: float = DEFAULT_REVERSE_TIMEOUT_S,
    tolerance_m: float = DEFAULT_TOLERANCE_M,
    stable_time_s: float = DEFAULT_STABLE_TIME_S,
    reverse_speed_m_s: float = DEFAULT_REVERSE_SPEED_M_S,
    rear_clearance_m: float = DEFAULT_REAR_CLEARANCE_M,
    kp: float = 0.75,
    kd: float = 0.22,
    max_lateral_speed: float = 0.24,
    yaw_kp: float = 2.0,
    max_yaw_speed: float = 8.0,
) -> bool:
    """Back along a wall until a stored point is reached.

    The wall-follow controller keeps the drone parallel and at range while the
    forward term runs negative. ``front_stop_distance`` is near zero because
    the front wall is irrelevant when reversing -- the rear is what matters,
    and that is checked directly against ``rear_clearance_m``.
    """
    controller = WallFollowController(
        side=side,
        target_distance=wall_distance,
        forward_speed=reverse_speed_m_s,
        front_stop_distance=0.1,
        kp=kp,
        kd=kd,
        max_lateral_speed=max_lateral_speed,
        yaw_kp=yaw_kp,
        max_yaw_speed=max_yaw_speed,
    )
    started = time.time()
    stable_since: float | None = None
    tick = 0

    while time.time() - started < timeout_s:
        pos = await drone.get_position()
        dist = math.hypot(
            float(target["x"]) - pos.position.north_m,
            float(target["y"]) - pos.position.east_m,
        )
        if dist <= tolerance_m:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= stable_time_s:
                await drone.set_velocity(VelocityCommand())
                print(f"  [reverse] reached leg start (err={dist:.2f}m)")
                return True
        else:
            stable_since = None

        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue
        if scan.rear_distance() < rear_clearance_m:
            await drone.set_velocity(VelocityCommand())
            print(f"  [reverse] rear clearance unsafe: {scan.rear_distance():.2f}m")
            return False

        wall_dist = scan.left_distance() if side == "left" else scan.right_distance()
        wall_angle = (
            scan.left_wall_angle_error() if side == "left" else scan.right_wall_angle_error()
        )
        cmd = controller.update(
            wall_dist=wall_dist,
            front_dist=scan.front_distance(),
            wall_angle_error=wall_angle,
            front_wall_confirmed=False,
            front_stop_reached=False,
        )
        await drone.set_velocity(cmd)
        tick += 1
        if tick % 10 == 0:
            print(
                f"  [reverse] err={dist:.2f}m fwd={cmd.forward_m_s:+.2f} "
                f"lat={cmd.right_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f} "
                f"{side}={wall_dist:.2f}m rear={scan.rear_distance():.2f}m"
            )
        await asyncio.sleep(0.05)

    await drone.set_velocity(VelocityCommand())
    print("  [reverse] timeout before reaching leg start")
    return False
