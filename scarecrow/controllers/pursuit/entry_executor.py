"""Async pursuit-entry movement helpers."""
from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Callable

from .entry_planner import camera_bearing_deg
from ..wall_follow import VelocityCommand, WallFollowController


def normalize_angle(deg: float) -> float:
    """Normalize an angle to [-180, 180] degrees."""
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _fmt_m(value: float | None, precision: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "?"
    return f"{value:.{precision}f}m"


async def rotate_to_yaw_until_target_observed(
    drone,
    tracker,
    target_yaw_deg: float,
    *,
    timeout_s: float,
    tolerance_deg: float,
    max_yaw_speed_deg_s: float,
    min_yaw_speed_deg_s: float,
    observation_max_age_s: float = 0.75,
    centered_bearing_deg: float = 30.0,
) -> dict:
    """Rotate slowly and stop once a fresh target frame is usable for pursuit."""
    started = time.time()
    stable_hits = 0
    final_yaw = math.nan
    final_error = math.inf
    last_status_s = -1.0
    while time.time() - started < timeout_s:
        now = time.time()
        observation = tracker.latest(max_age_s=observation_max_age_s, now=now)
        current_yaw = await drone.get_yaw()
        error = normalize_angle(target_yaw_deg - current_yaw)
        final_yaw = current_yaw
        final_error = error
        elapsed_s = now - started
        if elapsed_s - last_status_s >= 1.0:
            last_status_s = elapsed_s
            age = tracker.age
            age_text = "inf" if math.isinf(age) else f"{age:.1f}s"
            bearing_text = "?"
            if observation is not None:
                bearing = camera_bearing_deg(observation)
                if math.isfinite(bearing):
                    bearing_text = f"{bearing:+.1f}deg"
            print(
                "  [planner-yaw] "
                f"yaw={current_yaw:.1f} target={target_yaw_deg:.1f} "
                f"err={error:+.1f}deg target_age={age_text} "
                f"target_bearing={bearing_text}"
            )
        if observation is not None:
            bearing = camera_bearing_deg(observation)
            if math.isfinite(bearing) and abs(bearing) <= centered_bearing_deg:
                await drone.set_velocity(VelocityCommand())
                return {
                    "ok": True,
                    "reason": "target_usable",
                    "yaw_deg": current_yaw,
                    "target_yaw_deg": target_yaw_deg,
                    "yaw_error_deg": error,
                    "target_bearing_deg": bearing,
                    "elapsed_s": time.time() - started,
                    "observation": observation,
                }

        if abs(error) <= tolerance_deg:
            stable_hits += 1
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.15)
            if stable_hits >= 3:
                return {
                    "ok": True,
                    "reason": "yaw_reached",
                    "yaw_deg": current_yaw,
                    "target_yaw_deg": target_yaw_deg,
                    "yaw_error_deg": error,
                    "elapsed_s": time.time() - started,
                    "observation": None,
                }
            continue

        stable_hits = 0
        yaw_cmd = _clamp(error * 0.5, -max_yaw_speed_deg_s, max_yaw_speed_deg_s)
        if abs(yaw_cmd) < min_yaw_speed_deg_s:
            yaw_cmd = min_yaw_speed_deg_s if yaw_cmd >= 0 else -min_yaw_speed_deg_s
        await drone.set_velocity(VelocityCommand(yawspeed_deg_s=yaw_cmd))
        await asyncio.sleep(0.12)

    await drone.set_velocity(VelocityCommand())
    return {
        "ok": False,
        "reason": "timeout",
        "yaw_deg": final_yaw,
        "target_yaw_deg": target_yaw_deg,
        "yaw_error_deg": final_error,
        "elapsed_s": time.time() - started,
        "observation": None,
    }


async def advance_left_wall_by_local_distance(
    drone,
    lidar,
    distance_m: float,
    wall_distance: float,
    target_alt_m: float,
    *,
    heading_yaw_deg: float,
    timeout_s: float,
    forward_speed: float,
    wall_follow_kp: float,
    wall_follow_kd: float,
    wall_follow_max_lateral: float,
    wall_follow_yaw_kp: float,
    wall_follow_max_yaw: float,
    altitude_down_speed_fn: Callable[[float, float], tuple[float, float, bool]],
) -> tuple[str, float]:
    """Wall-follow until local displacement along heading reaches distance_m."""
    controller = WallFollowController(
        side="left",
        target_distance=wall_distance,
        forward_speed=forward_speed,
        front_stop_distance=wall_distance,
        kp=wall_follow_kp,
        kd=wall_follow_kd,
        max_lateral_speed=wall_follow_max_lateral,
        yaw_kp=wall_follow_yaw_kp,
        max_yaw_speed=wall_follow_max_yaw,
    )
    started = time.time()
    step = 0
    start_pos = await drone.get_position()
    start_x = start_pos.position.north_m
    start_y = start_pos.position.east_m
    heading_rad = math.radians(heading_yaw_deg)
    fwd_x = math.cos(heading_rad)
    fwd_y = math.sin(heading_rad)
    last_advanced_m = 0.0
    print(
        f"  [planner-advance] start_pos=N{start_x:.2f} E{start_y:.2f} "
        f"heading={heading_yaw_deg:.1f}deg target_delta={distance_m:.2f}m"
    )

    while time.time() - started < timeout_s:
        pos = await drone.get_position()
        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue

        current_front_m = scan.front_distance()
        advanced_m = (
            (pos.position.north_m - start_x) * fwd_x
            + (pos.position.east_m - start_y) * fwd_y
        )
        last_advanced_m = advanced_m
        if math.isfinite(advanced_m) and advanced_m >= distance_m:
            await drone.set_velocity(VelocityCommand())
            return "distance_reached", advanced_m

        wall_dist = scan.left_distance()
        wall_error = scan.left_wall_angle_error()
        cmd = controller.update(
            wall_dist=wall_dist,
            front_dist=current_front_m,
            wall_angle_error=wall_error,
            front_wall_confirmed=False,
            front_stop_reached=False,
        )
        agl = -(pos.position.down_m - drone.ground_z)
        cmd.down_m_s, _, _ = altitude_down_speed_fn(agl, target_alt_m)
        await drone.set_velocity(cmd)
        if step % 10 == 0:
            print(
                f"  [planner-advance] advanced={advanced_m:.2f}/{distance_m:.2f}m "
                f"left={wall_dist:.2f}m front={_fmt_m(current_front_m)} "
                f"fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} down={cmd.down_m_s:+.2f}"
            )
        if controller.done:
            await drone.set_velocity(VelocityCommand())
            return "front_wall", last_advanced_m

        step += 1
        await asyncio.sleep(0.05)

    await drone.set_velocity(VelocityCommand())
    if math.isfinite(last_advanced_m) and last_advanced_m >= distance_m:
        return "distance_reached", last_advanced_m
    return "timeout", last_advanced_m


async def wait_for_fresh_target_observation(
    tracker,
    *,
    timeout_s: float,
    max_age_s: float = 0.75,
    centered_bearing_deg: float | None = None,
):
    """Wait until the detector has produced a fresh post-handoff target observation."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        now = time.time()
        observation = tracker.latest(max_age_s=max_age_s, now=now)
        if observation is not None:
            if centered_bearing_deg is None:
                return observation
            bearing = camera_bearing_deg(observation)
            if math.isfinite(bearing) and abs(bearing) <= centered_bearing_deg:
                return observation
        await asyncio.sleep(0.05)
    observation = tracker.latest(max_age_s=max_age_s)
    if observation is None or centered_bearing_deg is None:
        return observation
    bearing = camera_bearing_deg(observation)
    if math.isfinite(bearing) and abs(bearing) <= centered_bearing_deg:
        return observation
    return None


__all__ = [
    "advance_left_wall_by_local_distance",
    "normalize_angle",
    "rotate_to_yaw_until_target_observed",
    "wait_for_fresh_target_observation",
]
