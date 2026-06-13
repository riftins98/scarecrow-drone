#!/usr/bin/env python3
"""Hangar circuit search with pigeon pursuit and live-only YOLO frames.

Combines the room traversal shell from corner_circuit.py with the reusable
wall-follow and target-pursuit behavior used by wall_follow_pigeon_pursuit.py.

Run with Gazebo already launched, for example:
    ./scripts/shell/launch_with_stream.sh hangar_lite
    .venv/bin/python scripts/flight/hangar_circuit_pursuit.py --ceiling-clearance 1.0
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict

# Keep webapp/live terminal output line-by-line even when this script is run
# outside DetectionService's `python -u` launcher path.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.controllers.distance_stabilizer import (  # noqa: E402
    DistanceStabilizerController,
    DistanceTargets,
)
from scarecrow.controllers.corner_approach import CornerApproachController  # noqa: E402
from scarecrow.controllers.pursuit.entry_executor import (  # noqa: E402
    advance_left_wall_by_local_distance,
    rotate_to_yaw_until_target_observed,
    wait_for_fresh_target_observation,
)
from scarecrow.controllers.pursuit import (  # noqa: E402
    PursuitEntryAction,
    PursuitEntryPlannerConfig,
    TargetPursuitConfig,
    TargetPursuitResult,
)
from scarecrow.controllers.pursuit.entry_planner import (  # noqa: E402
    bbox_width_px,
    camera_bearing_deg,
    plan_from_observation,
)
from scarecrow.controllers.rotation import rotate_90  # noqa: E402
from scarecrow.controllers.wall_follow import VelocityCommand, WallFollowController  # noqa: E402
from scarecrow.detection.tracking import TargetTracker  # noqa: E402
from scarecrow.detection.yolo import YoloDetector  # noqa: E402
from scarecrow.drone import Drone  # noqa: E402
from scarecrow.navigation.map_unit import MapUnit  # noqa: E402
from scarecrow.navigation.navigation_unit import NavigationUnit  # noqa: E402
from scarecrow.sensors.camera.gazebo import GazeboCamera  # noqa: E402
from scarecrow.sensors.gz_entities import (  # noqa: E402
    GzPx4FrameTransform,
    discover_model_name,
    discover_world_name,
    find_model_pose,
    get_world_model_poses,
    remove_nearest_model,
)
from scarecrow.sensors.gz_utils import prefetch_gz_env_async  # noqa: E402
from scarecrow.sensors.lidar.gazebo import GazeboLidar  # noqa: E402
from scarecrow.sensors.rangefinder import GazeboRangefinder  # noqa: E402


SYSTEM_ADDRESS = "udp://:14540"
DEFAULT_TARGET_DIST = 1.5
DEFAULT_WALL_DISTANCE = 2.0
DEFAULT_START_SIDE = "left"
DEFAULT_CEILING_CLEARANCE = 2.0
DEFAULT_HOVER_SECONDS = 5.0
DEFAULT_LEG_TIMEOUT = 300.0
DEFAULT_MAX_LEGS = 4
DEFAULT_PURSUIT_TIMEOUT = 75.0
DEFAULT_TARGET_MODEL_PREFIXES = ("pigeon",)
DEFAULT_TARGET_URI_KEYWORDS = ("pigeon",)
DEFAULT_IMAGE_WIDTH = 1280
YOLO_CONFIDENCE = 0.70
YOLO_PURSUIT_CONFIDENCE = 0.45
YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "yolov8s.pt")
MAX_PURSUIT_ATTEMPTS = 2
PURSUIT_ENTRY_ADVANCE_SCALE = 0.65
PURSUIT_ENTRY_PLANNER_CONFIG = PursuitEntryPlannerConfig(
    advance_scale=PURSUIT_ENTRY_ADVANCE_SCALE,
)
PLANNER_ADVANCE_TIMEOUT_S = 60.0
PLANNER_REACQUIRE_TIMEOUT_S = 4.0
PLANNER_ENTRY_YAW_SPEED_DEG_S = 6.0
PLANNER_ENTRY_YAW_MIN_SPEED_DEG_S = 2.0
PLANNER_ENTRY_YAW_CENTER_BEARING_DEG = 30.0
ALTITUDE_WARNING_ERROR_M = 0.20
ALTITUDE_HOLD_TOLERANCE_M = 0.12
ALTITUDE_HOLD_KP = 0.45
ALTITUDE_HOLD_MAX_DOWN_SPEED = 0.18

# Match the tuned wall-follow behavior used by room_circuit_map.py.
WALL_FOLLOW_SPEED = 0.30
WALL_FOLLOW_KP = 0.75
WALL_FOLLOW_KD = 0.22
WALL_FOLLOW_MAX_LATERAL = 0.24
WALL_FOLLOW_YAW_KP = 2.0
WALL_FOLLOW_MAX_YAW = 8.0

# Rotation/corner behavior borrowed from corner_circuit.py.
ROTATE_SPEED = 12.0
ROTATE_TOLERANCE = 5.0
ROTATE_TIMEOUT_S = 25.0
CORNER_TIMEOUT_S = 40.0

# Lightweight arena mapping/return behavior borrowed from room_circuit_map.py.
MAP_RECORD_EVERY = 10
ROUTE_SAMPLE_INTERVAL_S = 1.0
MAP_MIN_DIST = 0.2
MAP_MAX_DIST = 20.0
MAP_BOUNDARY_SAMPLE_TOLERANCE_M = 0.6
MAP_BOUNDARY_MIN_SIDE_SAMPLES = 2
RETURN_MAX_SPEED = 0.25
RETURN_KP = 0.35
RETURN_TOLERANCE_M = 0.35
RETURN_STABLE_TIME_S = 1.0
RETURN_TIMEOUT_S = 60.0
RETURN_BLOCKED_TIMEOUT_S = 5.0
RETURN_FRONT_CLEARANCE_M = 1.0
RETURN_REAR_CLEARANCE_M = 1.0
RETURN_SIDE_CLEARANCE_M = 0.8
REVERSE_WALL_SPEED = -0.20
REVERSE_TIMEOUT_S = 90.0
START_STABILIZE_TIMEOUT_S = 45.0
START_STABILIZE_MAX_SPEED = 0.16
START_STABILIZE_TOLERANCE_M = 0.15
START_STABILIZE_STABLE_TIME_S = 0.20
START_STABILIZE_MIN_CLEARANCE_M = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Circuit the hangar while detecting a pigeon, then pursue on sight."
    )
    parser.add_argument(
        "--flight-id",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--wall-distance",
        "--wall-dist",
        type=float,
        default=DEFAULT_WALL_DISTANCE,
        dest="wall_distance",
        help=(
            "Target distance to the followed wall in meters during circuit legs "
            f"(default: {DEFAULT_WALL_DISTANCE:.1f})."
        ),
    )
    parser.add_argument(
        "--ceiling-clearance",
        type=float,
        default=None,
        help=(
            "Optional minimum safe upward ceiling clearance in meters. When set, "
            "enforces ceiling safety after takeoff and during the mission. "
            f"Takeoff altitude always uses ceiling minus {DEFAULT_CEILING_CLEARANCE:.1f}m."
        ),
    )
    return parser.parse_args()


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _fmt_m(value: float | None, precision: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "?"
    return f"{value:.{precision}f}m"


def _fmt_altitude(altitude_ref: dict) -> str:
    agl = altitude_ref.get("agl_m")
    error = altitude_ref.get("error_m")
    if not isinstance(agl, (int, float)) or not math.isfinite(agl):
        return "agl=?"
    if not isinstance(error, (int, float)) or not math.isfinite(error):
        return f"agl={agl:.2f}m"
    return f"agl={agl:.2f}m alt_err={error:+.2f}m"


def _agl_from_position(pos, ground_z: float) -> float:
    return -(pos.position.down_m - ground_z)


def _altitude_hold_down_speed(
    agl_m: float,
    target_alt_m: float,
    *,
    tolerance_m: float = ALTITUDE_HOLD_TOLERANCE_M,
    kp: float = ALTITUDE_HOLD_KP,
    max_down_speed_m_s: float = ALTITUDE_HOLD_MAX_DOWN_SPEED,
) -> tuple[float, float, bool]:
    """Return vertical speed, altitude error, and in-band state.

    MAVSDK body velocity uses positive down speed for descent. A positive
    altitude error means the drone is too high and should descend.
    """
    if not math.isfinite(agl_m):
        return 0.0, math.inf, False
    error = agl_m - target_alt_m
    if abs(error) <= tolerance_m:
        return 0.0, error, True
    return _clamp(error * kp, -max_down_speed_m_s, max_down_speed_m_s), error, False


def _target_alt_from_ceiling_distance(
    ceiling_distance_m: float,
    *,
    target_clearance_m: float = DEFAULT_CEILING_CLEARANCE,
) -> float:
    """Return AGL target altitude that leaves requested upward clearance."""
    if not math.isfinite(ceiling_distance_m):
        raise ValueError("ceiling distance must be finite")
    if ceiling_distance_m <= target_clearance_m:
        raise ValueError(
            f"ceiling distance {ceiling_distance_m:.2f}m is not above "
            f"target clearance {target_clearance_m:.2f}m"
        )
    return ceiling_distance_m - target_clearance_m


def _normalize_angle(deg: float) -> float:
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


def _find_drone_camera_topic(topics: str) -> str | None:
    return next(
        (
            line.strip()
            for line in topics.splitlines()
            if "camera_link/sensor/camera/image" in line
            and "/model/holybro_x500" in line
        ),
        None,
    )


def _valid_distance(value: float, *, min_m: float, max_m: float) -> bool:
    return math.isfinite(value) and min_m <= value <= max_m


def _scan_valid_for_map(scan) -> bool:
    if scan is None or scan.num_samples == 0:
        return False
    distances = [
        scan.front_distance(),
        scan.rear_distance(),
        scan.left_distance(),
        scan.right_distance(),
    ]
    return all(_valid_distance(d, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST) for d in distances)


def _current_landing_targets(
    lidar: GazeboLidar,
    *,
    fallback_wall_distance: float,
) -> DistanceTargets:
    """Hold the current horizontal lidar position during landing."""
    scan = lidar.get_scan()
    if scan is None:
        return DistanceTargets(rear=fallback_wall_distance, left=fallback_wall_distance)

    rear = scan.rear_distance()
    left = scan.left_distance()
    if not _valid_distance(rear, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST):
        rear = fallback_wall_distance
    if not _valid_distance(left, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST):
        left = fallback_wall_distance
    return DistanceTargets(rear=rear, left=left)


def _nearest_start_side(scan, *, fallback_side: str = "left") -> str:
    """Pick the side wall that forms the nearest rear corner from current yaw."""
    left = scan.left_distance()
    right = scan.right_distance()
    left_valid = _valid_distance(left, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST)
    right_valid = _valid_distance(right, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST)
    if left_valid and right_valid:
        return "left" if left <= right else "right"
    if left_valid:
        return "left"
    if right_valid:
        return "right"
    return fallback_side


def _arena_boundary_from_start(
    *,
    x: float,
    y: float,
    yaw_deg: float,
    rear_distance: float,
    left_distance: float,
    front_distance: float,
    right_distance: float,
) -> list[dict]:
    """Build a simple box boundary from the stabilized circuit-start pose."""
    yaw_rad = math.radians(yaw_deg)
    fwd_x = math.cos(yaw_rad)
    fwd_y = math.sin(yaw_rad)
    right_x = -math.sin(yaw_rad)
    right_y = math.cos(yaw_rad)
    wall_points = [
        {"x": x + fwd_x * front_distance, "y": y + fwd_y * front_distance},
        {"x": x - fwd_x * rear_distance, "y": y - fwd_y * rear_distance},
        {"x": x - right_x * left_distance, "y": y - right_y * left_distance},
        {"x": x + right_x * right_distance, "y": y + right_y * right_distance},
    ]
    return MapUnit._axis_aligned_boundary(wall_points)


def _project_route_sample_wall_hit(sample: dict, side: str) -> dict | None:
    dist = sample.get(f"{side}_dist")
    if not isinstance(dist, (int, float)) or not math.isfinite(dist):
        return None
    if not _valid_distance(dist, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST):
        return None

    yaw_deg = sample.get("yaw_deg")
    x = sample.get("x")
    y = sample.get("y")
    if not all(isinstance(value, (int, float)) for value in (yaw_deg, x, y)):
        return None

    yaw_rad = math.radians(yaw_deg)
    fwd_x = math.cos(yaw_rad)
    fwd_y = math.sin(yaw_rad)
    right_x = -math.sin(yaw_rad)
    right_y = math.cos(yaw_rad)
    vectors = {
        "front": (fwd_x, fwd_y),
        "rear": (-fwd_x, -fwd_y),
        "left": (-right_x, -right_y),
        "right": (right_x, right_y),
    }
    vec_x, vec_y = vectors[side]
    return {
        "x": x + vec_x * dist,
        "y": y + vec_y * dist,
        "axis": "x" if abs(vec_x) >= abs(vec_y) else "y",
    }


def _refine_boundary_from_route_samples(
    boundaries: list[dict],
    route_samples: list[dict],
    *,
    wall_distance: float,
) -> list[dict]:
    """Adjust startup boundary sides using stable wall-follow evidence."""
    if len(boundaries) < 4:
        return boundaries

    xs = [point["x"] for point in boundaries]
    ys = [point["y"] for point in boundaries]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    candidates: dict[str, list[float]] = {
        "min_x": [],
        "max_x": [],
        "min_y": [],
        "max_y": [],
    }
    stable_phases = {"wall_follow", "reverse_leg", "stabilize_landing", "landing"}
    tolerance = max(MAP_BOUNDARY_SAMPLE_TOLERANCE_M, wall_distance * 0.2)

    for sample in route_samples:
        if sample.get("phase") not in stable_phases:
            continue
        for side in ("front", "rear", "left", "right"):
            dist = sample.get(f"{side}_dist")
            if not isinstance(dist, (int, float)) or not math.isfinite(dist):
                continue
            if abs(dist - wall_distance) > tolerance:
                continue
            hit = _project_route_sample_wall_hit(sample, side)
            if hit is None:
                continue
            if hit["axis"] == "x":
                key = "max_x" if hit["x"] >= center_x else "min_x"
                candidates[key].append(hit["x"])
            else:
                key = "max_y" if hit["y"] >= center_y else "min_y"
                candidates[key].append(hit["y"])

    refined = {
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
    }
    for key, values in candidates.items():
        if len(values) >= MAP_BOUNDARY_MIN_SIDE_SAMPLES:
            refined[key] = statistics.median(values)

    if refined["min_x"] >= refined["max_x"] or refined["min_y"] >= refined["max_y"]:
        return boundaries

    return [
        {"x": refined["min_x"], "y": refined["max_y"]},
        {"x": refined["min_x"], "y": refined["min_y"]},
        {"x": refined["max_x"], "y": refined["min_y"]},
        {"x": refined["max_x"], "y": refined["max_y"]},
    ]


async def record_map_sample(
    mapper: MapUnit,
    drone: Drone,
    lidar: GazeboLidar,
) -> bool:
    """Record one pose + lidar sample using PX4 local position and yaw."""
    scan = lidar.get_scan()
    if not _scan_valid_for_map(scan):
        return False

    pos = await drone.get_position()
    yaw_deg = await drone.get_yaw()
    mapper.record_position(scan, pos.position.north_m, pos.position.east_m, yaw_deg)
    mapper.record_wall_hits(
        scan,
        pos.position.north_m,
        pos.position.east_m,
        yaw_deg,
        min_m=MAP_MIN_DIST,
        max_m=MAP_MAX_DIST,
    )
    return True


async def record_pose_event(
    drone: Drone,
    events: list[dict],
    *,
    event_type: str,
    label: str,
    leg: int | None = None,
) -> dict:
    """Record a named map event at the current PX4 local position/yaw."""
    pos = await drone.get_position()
    yaw_deg = await drone.get_yaw()
    event = {
        "type": event_type,
        "label": label,
        "x": pos.position.north_m,
        "y": pos.position.east_m,
        "yaw_deg": yaw_deg,
        "timestamp": time.time(),
    }
    if leg is not None:
        event["leg"] = leg
    events.append(event)
    return event


async def route_sample_loop(
    drone: Drone,
    lidar: GazeboLidar,
    samples: list[dict],
    phase_ref: dict,
    stop_event: asyncio.Event,
    *,
    interval_s: float = ROUTE_SAMPLE_INTERVAL_S,
    target_alt_m: float | None = None,
    altitude_ref: dict | None = None,
    altitude_warning_error_m: float = ALTITUDE_WARNING_ERROR_M,
) -> None:
    """Record the live route once per second with a mission phase label."""
    while not stop_event.is_set():
        try:
            pos = await drone.get_position()
            yaw_deg = await drone.get_yaw()
            phase = phase_ref.get("phase", "unknown")
            agl = _agl_from_position(pos, drone.ground_z)
            alt_error = None if target_alt_m is None else agl - target_alt_m
            sample = {
                "x": pos.position.north_m,
                "y": pos.position.east_m,
                "yaw_deg": yaw_deg,
                "phase": phase,
                "agl_m": agl,
                "timestamp": time.time(),
            }
            if target_alt_m is not None:
                sample["target_alt_m"] = target_alt_m
                sample["alt_error_m"] = alt_error
            if altitude_ref is not None:
                altitude_ref["agl_m"] = agl
                altitude_ref["target_alt_m"] = target_alt_m
                altitude_ref["error_m"] = alt_error
                altitude_ref["phase"] = phase
            if (
                alt_error is not None
                and math.isfinite(alt_error)
                and abs(alt_error) >= altitude_warning_error_m
            ):
                print(
                    "  [altitude] WARNING "
                    f"phase={phase} agl={agl:.2f}m "
                    f"target={target_alt_m:.2f}m err={alt_error:+.2f}m"
                )
            scan = lidar.get_scan()
            if scan is not None:
                sample.update(
                    {
                        "front_dist": scan.front_distance(),
                        "rear_dist": scan.rear_distance(),
                        "left_dist": scan.left_distance(),
                        "right_dist": scan.right_distance(),
                    }
                )
            samples.append(sample)
        except Exception:
            pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            pass


async def fly_to_point_safely(
    drone: Drone,
    lidar: GazeboLidar,
    target: dict,
    *,
    label: str,
    timeout_s: float = RETURN_TIMEOUT_S,
    tolerance_m: float = RETURN_TOLERANCE_M,
    stable_time_s: float = RETURN_STABLE_TIME_S,
) -> dict:
    """Drive to a world N/E point with lidar-gated body-frame velocity."""
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

        yaw_rad = math.radians(current_yaw)
        fwd_error = n_err * math.cos(yaw_rad) + e_err * math.sin(yaw_rad)
        right_error = -n_err * math.sin(yaw_rad) + e_err * math.cos(yaw_rad)
        fwd = _clamp(RETURN_KP * fwd_error, -RETURN_MAX_SPEED, RETURN_MAX_SPEED)
        right = _clamp(RETURN_KP * right_error, -RETURN_MAX_SPEED, RETURN_MAX_SPEED)

        scan = lidar.get_scan()
        blocked = False
        if scan is None:
            blocked = True
            fwd = 0.0
            right = 0.0
        else:
            if fwd > 0.0 and scan.front_distance() < RETURN_FRONT_CLEARANCE_M:
                fwd = 0.0
            elif fwd < 0.0 and scan.rear_distance() < RETURN_REAR_CLEARANCE_M:
                fwd = 0.0

            if right > 0.0 and scan.right_distance() < RETURN_SIDE_CLEARANCE_M:
                right = 0.0
            elif right < 0.0 and scan.left_distance() < RETURN_SIDE_CLEARANCE_M:
                right = 0.0

            blocked = abs(fwd) < 0.01 and abs(right) < 0.01 and dist > tolerance_m

        if blocked:
            if blocked_since is None:
                blocked_since = time.time()
            elif time.time() - blocked_since >= RETURN_BLOCKED_TIMEOUT_S:
                await drone.set_velocity(VelocityCommand())
                print(f"  [{label}] blocked by lidar for {RETURN_BLOCKED_TIMEOUT_S:.1f}s")
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


async def rotate_to_yaw(
    drone: Drone,
    target_yaw_deg: float,
    *,
    timeout_s: float = ROTATE_TIMEOUT_S,
    tolerance_deg: float = ROTATE_TOLERANCE,
) -> dict:
    """Rotate in place until current PX4 yaw matches the stored yaw."""
    started = time.time()
    stable_hits = 0
    final_yaw = math.nan
    final_error = math.inf
    while time.time() - started < timeout_s:
        current_yaw = await drone.get_yaw()
        error = _normalize_angle(target_yaw_deg - current_yaw)
        final_yaw = current_yaw
        final_error = error
        if abs(error) <= tolerance_deg:
            stable_hits += 1
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.15)
            if stable_hits >= 3:
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
        yaw_cmd = _clamp(error * 0.8, -ROTATE_SPEED, ROTATE_SPEED)
        if abs(yaw_cmd) < 3.0:
            yaw_cmd = 3.0 if yaw_cmd >= 0 else -3.0
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


async def reverse_wall_follow_to_point(
    drone: Drone,
    lidar: GazeboLidar,
    target: dict,
    *,
    wall_distance: float,
    timeout_s: float = REVERSE_TIMEOUT_S,
    tolerance_m: float = RETURN_TOLERANCE_M,
    stable_time_s: float = RETURN_STABLE_TIME_S,
) -> bool:
    """Reverse along the left wall until the stored leg-start point is reached."""
    controller = WallFollowController(
        side="left",
        target_distance=wall_distance,
        forward_speed=REVERSE_WALL_SPEED,
        front_stop_distance=0.1,
        kp=WALL_FOLLOW_KP,
        kd=WALL_FOLLOW_KD,
        max_lateral_speed=WALL_FOLLOW_MAX_LATERAL,
        yaw_kp=WALL_FOLLOW_YAW_KP,
        max_yaw_speed=WALL_FOLLOW_MAX_YAW,
    )
    started = time.time()
    stable_since: float | None = None
    tick = 0

    while time.time() - started < timeout_s:
        pos = await drone.get_position()
        dist = math.hypot(float(target["x"]) - pos.position.north_m, float(target["y"]) - pos.position.east_m)
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
        if scan.rear_distance() < RETURN_REAR_CLEARANCE_M:
            await drone.set_velocity(VelocityCommand())
            print(f"  [reverse] rear clearance unsafe: {scan.rear_distance():.2f}m")
            return False

        cmd = controller.update(
            wall_dist=scan.left_distance(),
            front_dist=scan.front_distance(),
            wall_angle_error=scan.left_wall_angle_error(),
            front_wall_confirmed=False,
            front_stop_reached=False,
        )
        await drone.set_velocity(cmd)
        tick += 1
        if tick % 10 == 0:
            print(
                f"  [reverse] err={dist:.2f}m fwd={cmd.forward_m_s:+.2f} "
                f"lat={cmd.right_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f} "
                f"left={scan.left_distance():.2f}m rear={scan.rear_distance():.2f}m"
            )
        await asyncio.sleep(0.05)

    await drone.set_velocity(VelocityCommand())
    print("  [reverse] timeout before reaching leg start")
    return False


def _build_map_payload(
    mapper: MapUnit,
    events: list[dict],
    route_samples: list[dict],
    *,
    boundary_override: list[dict] | None = None,
    wall_distance: float = DEFAULT_WALL_DISTANCE,
) -> dict:
    result = mapper.finish_mapping()
    boundaries_json = result.get("boundaries", "[]")
    try:
        boundaries = json.loads(boundaries_json)
    except json.JSONDecodeError:
        boundaries = []
    if boundary_override:
        boundaries = boundary_override
        boundaries_json = json.dumps(boundaries)
    boundaries = _refine_boundary_from_route_samples(
        boundaries,
        route_samples,
        wall_distance=wall_distance,
    )
    boundaries_json = json.dumps(boundaries)
    return {
        "boundaries": boundaries,
        "boundaries_json": boundaries_json,
        "route": result.get("route", []),
        "route_json": json.dumps(result.get("route", [])),
        "takeoff_point": mapper.takeoff_point,
        "points": [asdict(p) for p in mapper.points],
        "route_samples": route_samples,
        "wall_points": result.get("wall_points", []),
        "events": events,
        "area_size": round(MapUnit._polygon_area(boundaries), 2),
    }


def _save_map_payload(payload: dict, output_dir: str) -> str:
    map_path = os.path.join(output_dir, "map.json")
    with open(map_path, "w") as fh:
        json.dump(payload, fh, indent=2)
    return map_path


async def _rotate_relative_simple(
    drone: Drone,
    lidar: GazeboLidar,
    degrees: float,
) -> bool:
    """Rotate 90 degrees using the package compass + lidar-SVD logic."""
    if not math.isclose(abs(degrees), 90.0, abs_tol=1e-6):
        raise ValueError("package rotation wrapper only supports +/-90 degrees")
    direction = "right" if degrees > 0.0 else "left"
    return await rotate_90(drone.system, lidar, direction=direction)


async def _approach_circuit_start_corner(
    drone: Drone,
    lidar: GazeboLidar,
    wall_distance: float,
    target_alt_m: float,
    timeout_s: float = START_STABILIZE_TIMEOUT_S,
) -> str | None:
    """Normalize launch pose to the start corner expected by left-wall scan.

    The circuit scan assumes the drone starts with a wall behind it and the
    followed wall on its left. If the initial pose is closer to the right-side
    rear corner, stabilize there first and let the caller rotate left.
    """
    first_scan = lidar.get_scan()
    if first_scan is None:
        print("  [hangar-circuit-start] ERROR: no lidar scan for start stabilization")
        return None

    side = _nearest_start_side(first_scan)
    print(
        f"  [hangar-circuit-start] nearest rear corner is {side}; "
        f"targeting rear={wall_distance:.1f}m {side}={wall_distance:.1f}m"
    )

    controller = CornerApproachController(
        side=side,
        rear_distance=wall_distance,
        side_distance=wall_distance,
        max_forward_speed=START_STABILIZE_MAX_SPEED,
        max_lateral_speed=START_STABILIZE_MAX_SPEED,
        max_total_speed=START_STABILIZE_MAX_SPEED,
        tolerance=START_STABILIZE_TOLERANCE_M,
        stable_time=START_STABILIZE_STABLE_TIME_S,
        min_clearance=START_STABILIZE_MIN_CLEARANCE_M,
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
        try:
            pos = await asyncio.wait_for(drone.get_position(), timeout=0.5)
            agl = _agl_from_position(pos, drone.ground_z)
        except Exception:
            agl = math.inf

        rear = scan.rear_distance()
        side_dist = scan.left_distance() if side == "left" else scan.right_distance()
        result = controller.update(scan)
        down_speed, alt_error, altitude_ok = _altitude_hold_down_speed(agl, target_alt_m)
        if altitude_ok:
            altitude_stable_hits += 1
        else:
            altitude_stable_hits = 0
        if result.unsafe:
            await drone.set_velocity(VelocityCommand())
            print(
                f"  [hangar-circuit-start] ABORT: unsafe clearance "
                f"rear={rear:.2f}m {side}={side_dist:.2f}m"
            )
            return None

        cmd = result.command
        cmd.down_m_s = down_speed
        await drone.set_velocity(cmd)
        if step % 20 == 0:
            print(
                f"  [hangar-circuit-start] {time.time() - started:.1f}s "
                f"rear={rear:.2f}m {side}={side_dist:.2f}m "
                f"agl={_fmt_m(agl, 2)} alt_err={alt_error:+.2f}m "
                f"cmd: fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} "
                f"down={cmd.down_m_s:+.2f}"
            )
        if result.done and altitude_stable_hits >= 3:
            await drone.set_velocity(VelocityCommand())
            print(
                f"  [hangar-circuit-start] LOCKED: "
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
            f"  [hangar-circuit-start] TIMEOUT: "
            f"rear={scan.rear_distance():.2f}m "
            f"left={scan.left_distance():.2f}m "
            f"right={scan.right_distance():.2f}m"
        )
    return None


async def _stabilize_corner(
    drone: Drone,
    lidar: GazeboLidar,
    wall_distance: float,
    target_alt_m: float,
    timeout_s: float = CORNER_TIMEOUT_S,
) -> bool:
    """Stabilize after a right turn using rear/left wall distances and altitude."""
    stabilizer = DistanceStabilizerController(
        targets=DistanceTargets(rear=wall_distance, left=wall_distance),
        max_forward_speed=0.30,
        max_lateral_speed=0.30,
        tolerance=0.15,
        stable_time=1.0,
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
        try:
            pos = await asyncio.wait_for(drone.get_position(), timeout=0.5)
            agl = _agl_from_position(pos, drone.ground_z)
        except Exception:
            agl = math.inf

        cmd = stabilizer.update(scan)
        down_speed, alt_error, altitude_ok = _altitude_hold_down_speed(agl, target_alt_m)
        if altitude_ok:
            altitude_stable_hits += 1
        else:
            altitude_stable_hits = 0
        cmd.down_m_s = down_speed
        await drone.set_velocity(cmd)
        if step % 10 == 0:
            print(
                f"  [corner] front={scan.front_distance():.2f}m "
                f"left={scan.left_distance():.2f}m "
                f"rear={scan.rear_distance():.2f}m "
                f"right={scan.right_distance():.2f}m "
                f"agl={_fmt_m(agl, 2)} alt_err={alt_error:+.2f}m "
                f"down={cmd.down_m_s:+.2f}"
            )
        if stabilizer.done and altitude_stable_hits >= 3:
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


async def _wait_for_rangefinder(rangefinder: GazeboRangefinder, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if rangefinder.get_distance_m() is not None:
            return True
        await asyncio.sleep(0.1)
    return False


async def _safe_land(drone: Drone) -> None:
    await drone.set_velocity(VelocityCommand())
    await drone.stop_offboard()
    print("Commanding land...")
    await drone.land()

    landed = False
    for _ in range(150):
        await asyncio.sleep(0.2)
        try:
            pos = await asyncio.wait_for(drone.get_position(), timeout=1.0)
        except Exception:
            break
        agl = -(pos.position.down_m - drone.ground_z)
        if agl < 0.15:
            landed = True
            break

    if not landed:
        print("  WARNING: touchdown not confirmed before disarm attempt")

    print("Disarming...")
    if await drone.disarm(force_kill_on_failure=landed):
        print("  Disarmed.")
    else:
        print("  WARNING: drone did not disarm cleanly")


async def run() -> None:
    args = parse_args()
    wall_distance = args.wall_distance
    ceiling_clearance = args.ceiling_clearance
    target_dist = DEFAULT_TARGET_DIST
    max_legs = max(1, DEFAULT_MAX_LEGS)
    flight_id = args.flight_id or f"hangar_circuit_pursuit_{int(time.time())}"
    output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 64)
    print("  SCARECROW DRONE - HANGAR CIRCUIT PURSUIT")
    print("=" * 64)
    print(f"Flight ID:         {flight_id}")
    print(f"Output:            {output_dir}")
    print(
        "Takeoff altitude:  auto "
        f"(ceiling - {DEFAULT_CEILING_CLEARANCE:.1f}m)"
    )
    print(f"Wall distance:     {wall_distance:.2f}m")
    print(f"Target distance:   {target_dist:.2f}m")
    print(f"Max legs:          {max_legs}")
    print("Camera recording:  disabled (live YOLO frames only)")
    if ceiling_clearance is not None:
        print(f"Min ceiling clear: {ceiling_clearance:.2f}m")

    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

    tracker = TargetTracker(image_width=DEFAULT_IMAGE_WIDTH)
    detector = YoloDetector(
        model_path=YOLO_MODEL_PATH,
        output_dir=output_dir,
        confidence=YOLO_CONFIDENCE,
        on_detection_data=tracker.update_from_yolo,
        target_classes=("bird", "pigeon"),
    )
    detector.configure_saving(save_detections=False, save_no_detections=False)
    yolo_thread = detector.preload_async()
    gz_thread, gz_result = prefetch_gz_env_async()

    drone = Drone(system_address=SYSTEM_ADDRESS)
    nav: NavigationUnit | None = None
    lidar: GazeboLidar | None = None
    camera: GazeboCamera | None = None
    ceiling_sensor: GazeboRangefinder | None = None
    mapper = MapUnit()
    map_events: list[dict] = []
    map_tasks: list[asyncio.Task] = []
    route_samples: list[dict] = []
    route_phase = {"phase": "wall_follow"}
    target_alt: float | None = None
    altitude_ref: dict = {"agl_m": None, "target_alt_m": None, "error_m": None}
    route_stop_event = asyncio.Event()
    route_task: asyncio.Task | None = None
    map_saved = False
    arena_boundary: list[dict] | None = None

    try:
        print("\nConnecting to drone...")
        if not await drone.connect():
            print("ERROR: could not connect to drone")
            return
        print("Connected.")

        await drone.set_ekf_origin()

        print("Waiting for position estimate...")
        if not await drone.wait_for_health():
            print("ERROR: position estimate timed out")
            return
        print("Position OK.")

        print("\n--- Sensor verification ---")
        if not await drone.verify_gps_denied_params(verbose=True):
            print("Sensor config mismatch -- aborting")
            return

        yolo_thread.join(timeout=30)
        gz_thread.join(timeout=10)
        gz_env = gz_result.env or {}
        topics = gz_result.topics
        sim_world = discover_world_name(topics)
        drone_model_name = discover_model_name(topics, contains="holybro_x500") or "holybro_x500"
        target_model_prefixes = DEFAULT_TARGET_MODEL_PREFIXES
        target_uri_keywords = DEFAULT_TARGET_URI_KEYWORDS
        if sim_world:
            print(f"  Gazebo world: {sim_world}")
        else:
            print("  WARNING: Gazebo world name not found; target removal will be skipped")
        print(f"  Gazebo drone model: {drone_model_name}")

        print("\nStarting 2D lidar...")
        lidar = GazeboLidar(env=gz_env, num_threads=3)
        lidar._topic = lidar._discover_topic(topic_list=topics)
        lidar.start()
        print(f"  Lidar topic: {lidar.topic}")

        print("Starting upward ceiling rangefinder...")
        ceiling_sensor = GazeboRangefinder(env=gz_env)
        try:
            # Do not reuse the prefetched topic list here — the upward sensor
            # topic often appears a few seconds after the 2D lidar.
            ceiling_sensor.start(discover_timeout_s=30.0)
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            print(
                "  Hint: confirm model://tf_luna_up is on the drone "
                "(gz topic -l | grep ceiling_rangefinder)"
            )
            return
        print(f"  Ceiling topic: {ceiling_sensor.topic}")
        if not await _wait_for_rangefinder(ceiling_sensor):
            print("ERROR: no upward rangefinder data -- aborting")
            return
        ceiling_distance = ceiling_sensor.get_distance_m()
        if ceiling_distance is None:
            print("ERROR: no upward rangefinder distance for auto altitude -- aborting")
            return
        try:
            target_alt = _target_alt_from_ceiling_distance(ceiling_distance)
        except ValueError as exc:
            print(f"ERROR: cannot compute takeoff altitude: {exc}")
            return
        altitude_ref["target_alt_m"] = target_alt
        print(
            "  Auto takeoff altitude: "
            f"ceiling={ceiling_distance:.2f}m - "
            f"clearance={DEFAULT_CEILING_CLEARANCE:.2f}m -> "
            f"{target_alt:.2f}m AGL"
        )

        for _ in range(30):
            await asyncio.sleep(0.1)
            scan = lidar.get_scan()
            if scan is not None:
                print(
                    f"  Lidar ready: rear={scan.rear_distance():.1f}m "
                    f"left={scan.left_distance():.1f}m "
                    f"front={scan.front_distance():.1f}m "
                    f"right={scan.right_distance():.1f}m"
                )
                break
        else:
            print("ERROR: no lidar data -- aborting")
            return

        print(f"\nSetting takeoff altitude to {target_alt:.2f}m...")
        takeoff_origin = await drone.prepare_takeoff(target_alt)

        print("Arming...")
        await drone.arm()
        print("Armed.")

        print(f"Taking off to {target_alt:.2f}m with PX4...")
        if not await drone.takeoff(altitude=target_alt):
            print("ERROR: takeoff failed")
            return

        if not await drone.start_offboard():
            print("ERROR: offboard start failed")
            return

        nav = NavigationUnit(drone, lidar)

        print("\n--- Phase 1: approach circuit start corner ---")
        start_side = await _approach_circuit_start_corner(
            drone,
            lidar,
            wall_distance,
            target_alt,
        )
        if start_side is None:
            print("ERROR: start stabilization failed. Landing safely.")
            return
        if start_side == "right":
            print("  [hangar-circuit-start] right-side corner selected; rotating left to start scan")
            if not await _rotate_relative_simple(drone, lidar, -90.0):
                print("ERROR: start heading normalization failed. Landing safely.")
                return
        mapper.start_mapping()
        route_task = asyncio.create_task(
            route_sample_loop(
                drone,
                lidar,
                route_samples,
                route_phase,
                route_stop_event,
                target_alt_m=target_alt,
                altitude_ref=altitude_ref,
            )
        )
        mapper.set_takeoff_point(
            takeoff_origin.position.north_m,
            takeoff_origin.position.east_m,
        )
        circuit_start_pos = await drone.get_position()
        circuit_start_yaw = await drone.get_yaw()
        frame_transform: GzPx4FrameTransform | None = None
        if sim_world:
            live_poses = get_world_model_poses(world_name=sim_world, env=gz_env)
            gz_drone_pose = find_model_pose(
                live_poses,
                name=drone_model_name,
                contains="holybro_x500",
            )
            if gz_drone_pose is not None:
                frame_transform = GzPx4FrameTransform(
                    px4_origin_x=circuit_start_pos.position.north_m,
                    px4_origin_y=circuit_start_pos.position.east_m,
                    px4_origin_yaw_deg=circuit_start_yaw,
                    gz_origin_x=gz_drone_pose.x,
                    gz_origin_y=gz_drone_pose.y,
                    gz_origin_yaw_deg=gz_drone_pose.yaw_deg,
                )
                print(
                    "  PX4/Gazebo frame calibrated: "
                    f"px4=({frame_transform.px4_origin_x:.2f},"
                    f"{frame_transform.px4_origin_y:.2f},"
                    f"{frame_transform.px4_origin_yaw_deg:.1f}deg) "
                    f"gz=({frame_transform.gz_origin_x:.2f},"
                    f"{frame_transform.gz_origin_y:.2f},"
                    f"{frame_transform.gz_origin_yaw_deg:.1f}deg) "
                    f"yaw_offset={frame_transform.yaw_offset_deg:.1f}deg"
                )
            else:
                print("  WARNING: live Gazebo drone pose not found; target removal will be skipped")
        mapper.record_corner(circuit_start_pos.position.north_m, circuit_start_pos.position.east_m)
        map_events.append(
            {
                "type": "circuit_start",
                "label": "Circuit start",
                "x": circuit_start_pos.position.north_m,
                "y": circuit_start_pos.position.east_m,
                "yaw_deg": circuit_start_yaw,
                "timestamp": time.time(),
            }
        )
        start_scan = lidar.get_scan()
        if start_scan is not None:
            front_distance = start_scan.front_distance()
            right_distance = start_scan.right_distance()
            if not _valid_distance(front_distance, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST):
                front_distance = wall_distance
            if not _valid_distance(right_distance, min_m=MAP_MIN_DIST, max_m=MAP_MAX_DIST):
                right_distance = wall_distance
            arena_boundary = _arena_boundary_from_start(
                x=circuit_start_pos.position.north_m,
                y=circuit_start_pos.position.east_m,
                yaw_deg=circuit_start_yaw,
                rear_distance=wall_distance,
                left_distance=wall_distance,
                front_distance=front_distance,
                right_distance=right_distance,
            )
        await record_map_sample(mapper, drone, lidar)

        if ceiling_clearance is not None:
            print("\n--- Phase 2: ceiling safety check ---")
            result = nav.check_ceiling_clearance(
                ceiling_sensor=ceiling_sensor,
                min_clearance_m=ceiling_clearance,
            )
            if not result.done:
                print(f"  Ceiling safety check failed: {result.reason}")
                return
            print(f"  Ceiling clearance safe: {result.clearance_m:.2f}m")

        cam_topic = _find_drone_camera_topic(topics)
        if cam_topic is None:
            print("ERROR: drone camera topic not found")
            return
        camera = GazeboCamera(topic=cam_topic, env=gz_env)
        camera.start()
        print(f"  Camera topic: {camera.topic}")

        detection_enabled = False
        target_removal_event: dict | None = None
        pursuit_count = 0
        suppress_target_until_lost = False
        suppress_target_started_at = 0.0

        def set_detection_enabled(enabled: bool, reason: str) -> None:
            nonlocal detection_enabled
            if enabled == detection_enabled:
                return

            detection_enabled = enabled
            if enabled:
                camera.on_frame = detector.process_frame
                detector.start()
                print(f"  Detection enabled: {reason}")
            else:
                detector.stop()
                camera.on_frame = None
                print(f"  Detection disabled: {reason}")

        def ceiling_safe_or_stop() -> str | None:
            if ceiling_clearance is None:
                return None
            result = nav.check_ceiling_clearance(
                ceiling_sensor=ceiling_sensor,
                min_clearance_m=ceiling_clearance,
            )
            return None if result.done else result.reason

        async def pursue_and_finish(leg: int, attempt: int) -> TargetPursuitResult:
            nonlocal pursuit_count, target_removal_event
            target_removal_event = None
            pursuit_count += 1
            pursuit_label = (
                f"leg{leg:02d}_Pursuit{pursuit_count:02d}_attermpt_{attempt:02d}"
            )
            route_phase["phase"] = "pursuit"
            print(
                f"\n--- Phase 4: pursue pigeon to {target_dist:.2f}m "
                f"(attempt {attempt}/{MAX_PURSUIT_ATTEMPTS}) ---"
            )
            detector.confidence = YOLO_PURSUIT_CONFIDENCE
            detector.configure_saving(
                save_detections=False,
                save_no_detections=False,
                max_saved_detections=None,
                detection_prefix=pursuit_label,
                reset_counter=True,
            )
            detector.capture_next_detection(f"{pursuit_label}_start")
            print(f"  Detection threshold: {YOLO_PURSUIT_CONFIDENCE:.0%} for pursuit/relocalization")
            centered_image_requested = False

            def on_pursuit_status(result: TargetPursuitResult) -> None:
                nonlocal centered_image_requested
                if (
                    not centered_image_requested
                    and result.state.value == "APPROACHING"
                ):
                    centered_image_requested = True
                    detector.capture_next_detection(f"{pursuit_label}_centered")
                    print("  [pursuit] centered image queued before approach")

                important_state = result.state.value in {
                    "SEARCHING",
                    "LOST",
                    "TIMEOUT",
                    "WALL_SAFETY",
                    "TARGET_REACHED",
                }
                if not important_state and int(result.elapsed_s * 10) % 20 != 0:
                    return
                front = "?" if result.front_distance_m is None else f"{result.front_distance_m:.2f}m"
                age = "?" if result.target_age_s is None else f"{result.target_age_s:.1f}s"
                center = (
                    "?"
                    if result.center_error_ratio is None
                    else f"{result.center_error_ratio:.2f}"
                )
                vertical = (
                    "?"
                    if result.vertical_error_ratio is None
                    else f"{result.vertical_error_ratio:+.2f}"
                )
                print(
                    f"  [{result.elapsed_s:5.1f}s] {result.state.value} "
                    f"front={front} age={age} center_err={center} vert_err={vertical} "
                    f"down={result.command.down_m_s:+.2f} yaw={result.command.yawspeed_deg_s:+.1f} "
                    f"{_fmt_altitude(altitude_ref)} reason={result.reason}"
                )

            def on_search_status(event: str, data: dict[str, object]) -> None:
                if event == "start":
                    front = data.get("front_distance_m")
                    age = data.get("target_age_s")
                    front_text = "?" if front is None else f"{float(front):.2f}m"
                    age_text = "?" if age is None else f"{float(age):.1f}s"
                    print(
                        "  [search] target lost; starting sweep "
                        f"front={front_text} last_age={age_text}"
                    )
                elif event == "hover":
                    print("  [search] hover before relocalization")
                elif event == "sweep_start":
                    print(
                        "  [search] sweep "
                        f"{data.get('direction')} "
                        f"angle={float(data['angle_deg']):.1f}deg "
                        f"yaw={float(data['yaw_speed_deg_s']):+.1f}deg/s "
                        f"duration={float(data['duration_s']):.1f}s"
                    )
                elif event == "sweep_reacquired":
                    print(f"  [search] target reacquired during {data.get('direction')} sweep")
                elif event == "sweep_end":
                    print(
                        "  [search] sweep "
                        f"{data.get('direction')} ended found={data.get('found')}"
                    )
                elif event == "reacquired":
                    print("  [search] relocalization complete; resuming pursuit")
                elif event == "wall_safety_abort":
                    print(
                        "  [search] abort: wall safety "
                        f"left={float(data['left_distance_m']):.2f}m "
                        f"right={float(data['right_distance_m']):.2f}m"
                    )
                elif event == "failed":
                    print("  [search] relocalization failed; pursuit will end safely")

            pursuit_result = await nav.pursue_target(
                tracker=tracker,
                config=TargetPursuitConfig(
                    target_distance_m=target_dist,
                    max_forward_speed_m_s=0.40,
                    min_forward_speed_m_s=0.10,
                    kp_forward=0.40,
                    yaw_kp=22.0,
                    max_yaw_speed_deg_s=32.0,
                    vertical_kp=0.50,
                    max_vertical_speed_m_s=0.32,
                    pursuit_timeout_s=args.pursuit_timeout,
                    center_enter_ratio=0.50,
                    center_exit_ratio=0.60,
                    vertical_center_enter_ratio=0.10,
                    vertical_center_exit_ratio=0.16,
                    detection_miss_timeout_s=2.5,
                    detection_miss_count_required=3,
                ),
                on_status=on_pursuit_status,
                on_search_status=on_search_status,
            )
            if not pursuit_result.reached_target:
                print(f"  Pursuit ended without reaching target: {pursuit_result.reason}")
                failure_pos = await drone.get_position()
                failure_yaw = await drone.get_yaw()
                map_events.append(
                    {
                        "type": "pursuit_attempt_failed",
                        "label": (
                            f"Pursuit attempt {attempt}/{MAX_PURSUIT_ATTEMPTS} "
                            f"failed on leg {leg}"
                        ),
                        "x": failure_pos.position.north_m,
                        "y": failure_pos.position.east_m,
                        "yaw_deg": failure_yaw,
                        "reason": pursuit_result.reason,
                        "attempt": attempt,
                        "max_attempts": MAX_PURSUIT_ATTEMPTS,
                        "success": False,
                        "timestamp": time.time(),
                        "leg": leg,
                    }
                )
                return pursuit_result

            print(
                "  Target reached at "
                f"{pursuit_result.front_distance_m:.2f}m. "
                f"Hovering {DEFAULT_HOVER_SECONDS:.1f}s."
            )
            detector.capture_next_detection(f"{pursuit_label}_reached")
            target_pos = await drone.get_position()
            target_yaw = await drone.get_yaw()
            if frame_transform is not None:
                target_world_x, target_world_y = frame_transform.estimate_target_gz_xy(
                    local_x=target_pos.position.north_m,
                    local_y=target_pos.position.east_m,
                    yaw_deg=target_yaw,
                    range_m=pursuit_result.front_distance_m,
                )
                target_removal_event = {
                    "x": target_world_x,
                    "y": target_world_y,
                    "local_x": target_pos.position.north_m,
                    "local_y": target_pos.position.east_m,
                    "yaw_deg": target_yaw,
                    "range_m": pursuit_result.front_distance_m,
                    "leg": leg,
                }
            else:
                target_removal_event = None
            map_events.append(
                {
                    "type": "target_reached",
                    "label": f"Target reached at {target_dist:.2f}m",
                    "x": target_pos.position.north_m,
                    "y": target_pos.position.east_m,
                    "yaw_deg": target_yaw,
                    "distance_m": pursuit_result.front_distance_m,
                    "success": True,
                    "attempt": attempt,
                    "timestamp": time.time(),
                    "leg": leg,
                }
            )
            await nav.hover(DEFAULT_HOVER_SECONDS)
            return pursuit_result

        async def return_to_pursuit_entry(
            pursuit_entry_point: dict,
            leg: int,
            attempt: int,
            outcome: str,
        ) -> tuple[dict, dict] | None:
            print("\n--- Phase 5: return to pursuit entry ---")
            route_phase["phase"] = "return_entry"
            entry_return_result = await fly_to_point_safely(
                drone,
                lidar,
                pursuit_entry_point,
                label="return-entry",
            )
            map_events.append(
                {
                    "type": "pursuit_entry_returned",
                    "label": f"Returned to pursuit entry on leg {leg}",
                    "target_x": pursuit_entry_point["x"],
                    "target_y": pursuit_entry_point["y"],
                    "target_yaw_deg": pursuit_entry_point["yaw_deg"],
                    "x": entry_return_result["x"],
                    "y": entry_return_result["y"],
                    "yaw_deg": entry_return_result["yaw_deg"],
                    "position_error_m": entry_return_result["error_m"],
                    "return_ok": entry_return_result["ok"],
                    "return_reason": entry_return_result["reason"],
                    "elapsed_s": entry_return_result["elapsed_s"],
                    "attempt": attempt,
                    "outcome": outcome,
                    "timestamp": time.time(),
                    "leg": leg,
                }
            )
            if not entry_return_result["ok"]:
                print("  WARNING: could not return to pursuit entry; landing at current position")
                return None

            print("\n--- Phase 6: restore pre-pursuit heading ---")
            route_phase["phase"] = "restore_heading"
            heading_result = await rotate_to_yaw(drone, float(pursuit_entry_point["yaw_deg"]))
            map_events.append(
                {
                    "type": "pursuit_heading_restored",
                    "label": f"Restored pursuit entry heading on leg {leg}",
                    "x": entry_return_result["x"],
                    "y": entry_return_result["y"],
                    "yaw_deg": heading_result["yaw_deg"],
                    "target_yaw_deg": heading_result["target_yaw_deg"],
                    "yaw_error_deg": heading_result["yaw_error_deg"],
                    "heading_ok": heading_result["ok"],
                    "heading_reason": heading_result["reason"],
                    "elapsed_s": heading_result["elapsed_s"],
                    "attempt": attempt,
                    "outcome": outcome,
                    "timestamp": time.time(),
                    "leg": leg,
                }
            )
            if not heading_result["ok"]:
                print("  WARNING: heading restore timed out; resuming scan from current heading")
            return entry_return_result, heading_result

        print("\n--- Phase 3: circuit wall-follow with detection ---")
        leg = 1
        while leg <= max_legs:
            route_phase["phase"] = "wall_follow"
            print(f"\n--- Leg {leg}/{max_legs}: follow left wall and watch for pigeon ---")
            leg_start_pos = await drone.get_position()
            leg_start_yaw = await drone.get_yaw()
            current_leg_start_point = {
                "type": "leg_start",
                "label": f"Leg {leg} start",
                "x": leg_start_pos.position.north_m,
                "y": leg_start_pos.position.east_m,
                "yaw_deg": leg_start_yaw,
                "timestamp": time.time(),
                "leg": leg,
            }
            if not mapper.corners or (
                abs(mapper.corners[-1]["x"] - current_leg_start_point["x"]) > 0.05
                or abs(mapper.corners[-1]["y"] - current_leg_start_point["y"]) > 0.05
            ):
                mapper.record_corner(current_leg_start_point["x"], current_leg_start_point["y"])
            map_events.append(current_leg_start_point)

            detector.confidence = YOLO_CONFIDENCE
            detector.configure_saving(
                save_detections=False,
                save_no_detections=False,
                reset_counter=True,
            )
            detector.capture_next_detection(
                f"leg{leg:02d}_Pursuit{pursuit_count + 1:02d}_attermpt_01_trigger"
            )
            print(f"  Detection threshold: {YOLO_CONFIDENCE:.0%} for wall-follow trigger")
            tracker.clear()
            set_detection_enabled(True, "wall-follow leg")
            wall_stop_reason = "target_detected"
            wall_status_tick = 0
            last_suppressed_detection_log_s = 0.0

            def stop_condition() -> bool:
                nonlocal wall_stop_reason, suppress_target_until_lost, last_suppressed_detection_log_s
                now = time.time()
                latest_target = tracker.latest(max_age_s=1.5, now=now)
                if suppress_target_until_lost:
                    if latest_target is None and now - suppress_target_started_at >= 2.0:
                        suppress_target_until_lost = False
                        print("  Detection suppression cleared: failed target no longer visible")
                    elif latest_target is not None and now - last_suppressed_detection_log_s >= 1.0:
                        last_suppressed_detection_log_s = now
                        print(
                            "  [planner] not entering pursuit: "
                            "reason=target_suppressed_until_lost "
                            f"confidence={latest_target.confidence:.0%}"
                        )
                elif latest_target is not None:
                    wall_stop_reason = "target_detected"
                    print(
                        "  [target candidate] acquired "
                        f"confidence={latest_target.confidence:.0%}; "
                        "stopping XY for pre-pursuit planner"
                    )
                    return True
                safety_reason = ceiling_safe_or_stop()
                if safety_reason is not None:
                    wall_stop_reason = safety_reason
                    return True
                return False

            def on_wall_status(result) -> None:
                nonlocal wall_status_tick
                wall_status_tick += 1
                if wall_status_tick % 10 != 0 and not result.done:
                    return
                if wall_status_tick % MAP_RECORD_EVERY == 0 or result.done:
                    map_tasks.append(
                        asyncio.create_task(record_map_sample(mapper, drone, lidar))
                    )
                cmd = result.command or VelocityCommand()
                print(
                    f"  [leg {leg} {result.elapsed_s:5.1f}s] "
                    f"fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} "
                    f"down={cmd.down_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f} | "
                    f"left={_fmt_m(result.wall_distance_m)} "
                    f"front={_fmt_m(result.front_distance_m)} "
                    f"raw_front={_fmt_m(result.raw_front_distance_m)} "
                    f"visible={result.front_wall_visible} "
                    f"{_fmt_altitude(altitude_ref)}"
                )

            wall_result = await nav.wall_follow_until(
                side="left",
                target_distance=wall_distance,
                forward_speed=WALL_FOLLOW_SPEED,
                front_stop_distance=wall_distance,
                timeout=DEFAULT_LEG_TIMEOUT,
                stop_condition=stop_condition,
                on_status=on_wall_status,
                kp=WALL_FOLLOW_KP,
                kd=WALL_FOLLOW_KD,
                max_lateral_speed=WALL_FOLLOW_MAX_LATERAL,
                yaw_kp=WALL_FOLLOW_YAW_KP,
                max_yaw_speed=WALL_FOLLOW_MAX_YAW,
                target_alt_m=target_alt,
                altitude_kp=ALTITUDE_HOLD_KP,
                altitude_tolerance_m=ALTITUDE_HOLD_TOLERANCE_M,
                max_vertical_speed_m_s=ALTITUDE_HOLD_MAX_DOWN_SPEED,
            )
            print(
                f"  Leg {leg} ended: {wall_result.reason} "
                f"(left={_fmt_m(wall_result.wall_distance_m)}, "
                f"front={_fmt_m(wall_result.front_distance_m)}, "
                f"raw_front={_fmt_m(wall_result.raw_front_distance_m)})"
            )

            if wall_result.reason == "interrupted" and wall_stop_reason == "target_detected":
                if map_tasks:
                    await asyncio.gather(*map_tasks, return_exceptions=True)
                    map_tasks.clear()

                set_detection_enabled(False, "target acquired; planning pursuit entry")
                planner_failed = False
                route_phase["phase"] = "pursuit_entry_planner"
                planner_observation = tracker.latest(max_age_s=2.5)
                if planner_observation is None:
                    planner_failed = True
                    suppress_target_until_lost = True
                    suppress_target_started_at = time.time()
                    print(
                        "  [planner] not entering pursuit: "
                        "reason=no_fresh_target_observation max_age=2.5s"
                    )
                else:
                    decision = plan_from_observation(
                        planner_observation,
                        PURSUIT_ENTRY_PLANNER_CONFIG,
                    )
                    print(
                        "  [planner] image geometry: "
                        f"bbox_w={decision.bbox_width_px:.0f}px "
                        f"bearing={decision.bearing_deg:.1f}deg "
                        f"signed={decision.camera_bearing_deg:+.1f}deg "
                        f"range_est={_fmt_m(decision.range_estimate_m)} "
                        f"side_est={_fmt_m(decision.side_estimate_m)} "
                        f"forward_est={_fmt_m(decision.forward_estimate_m)} "
                        f"target_bearing={decision.target_bearing_deg:.1f}deg "
                        "advance="
                        f"{_fmt_m(decision.advance_m if math.isfinite(decision.advance_m) else decision.required_advance_m)} "
                        f"required_advance={_fmt_m(decision.required_advance_m)} "
                        f"advance_scale={PURSUIT_ENTRY_ADVANCE_SCALE:.2f} "
                        f"decision={decision.action.value}:{decision.reason}"
                    )

                    if decision.action == PursuitEntryAction.REJECT:
                        planner_failed = True
                        suppress_target_until_lost = True
                        suppress_target_started_at = time.time()
                        print(
                            "  [planner] not entering pursuit: "
                            f"reason=planner_reject:{decision.reason} "
                            f"bbox_w={decision.bbox_width_px:.0f}px "
                            f"bearing={decision.camera_bearing_deg:+.1f}deg "
                            f"range_est={_fmt_m(decision.range_estimate_m)} "
                            f"side_est={_fmt_m(decision.side_estimate_m)} "
                            f"required_advance={_fmt_m(decision.required_advance_m)}"
                        )
                    elif decision.action == PursuitEntryAction.ADVANCE:
                        advance_m = decision.advance_m
                        detector.confidence = YOLO_CONFIDENCE
                        tracker.clear()
                        print("  [planner] restoring wall-follow heading")
                        heading_result = await rotate_to_yaw(drone, leg_start_yaw)
                        if not heading_result["ok"]:
                            print("  WARNING: planner heading restore timed out")

                        route_phase["phase"] = "pursuit_entry_advance"
                        print(
                            "  [planner] advancing along wall "
                            f"{advance_m:.1f}m before original pursuit"
                        )
                        advance_reason, advanced_m = await advance_left_wall_by_local_distance(
                            drone,
                            lidar,
                            advance_m,
                            args.wall_distance,
                            args.target_alt,
                            heading_yaw_deg=leg_start_yaw,
                            timeout_s=PLANNER_ADVANCE_TIMEOUT_S,
                            forward_speed=WALL_FOLLOW_SPEED,
                            wall_follow_kp=WALL_FOLLOW_KP,
                            wall_follow_kd=WALL_FOLLOW_KD,
                            wall_follow_max_lateral=WALL_FOLLOW_MAX_LATERAL,
                            wall_follow_yaw_kp=WALL_FOLLOW_YAW_KP,
                            wall_follow_max_yaw=WALL_FOLLOW_MAX_YAW,
                            altitude_down_speed_fn=_altitude_hold_down_speed,
                        )
                        print(
                            "  [planner] advance ended: "
                            f"{advance_reason} "
                            f"(advanced={advanced_m:.2f}m)"
                        )
                        tracker.clear()
                        if advance_reason == "front_wall":
                            planner_failed = True
                            print(
                                "  [planner] not entering pursuit: "
                                f"reason=entry_advance_front_wall "
                                f"advanced={advanced_m:.2f}m required={advance_m:.2f}m"
                            )
                        elif advance_reason != "distance_reached":
                            planner_failed = True
                            print(
                                "  [planner] not entering pursuit: "
                                f"reason=entry_advance_{advance_reason} "
                                f"advanced={advanced_m:.2f}m required={advance_m:.2f}m"
                            )
                    else:
                        print("  [planner] target already has sufficient entry bearing")

                if planner_failed:
                    route_phase["phase"] = "wall_follow"
                    continue

                detector.confidence = YOLO_PURSUIT_CONFIDENCE
                detector.configure_saving(
                    save_detections=False,
                    save_no_detections=False,
                    max_saved_detections=None,
                    reset_counter=True,
                )
                tracker.clear()
                set_detection_enabled(True, "planner entry-yaw detection")
                await asyncio.sleep(0.30)

                reacquired_observation = None
                entry_yaw_delta_deg = decision.entry_yaw_delta_deg
                if math.isfinite(entry_yaw_delta_deg):
                    planned_entry_yaw_deg = _normalize_angle(
                        leg_start_yaw + entry_yaw_delta_deg
                    )
                    route_phase["phase"] = "pursuit_entry_yaw"
                    print(
                        "  [planner] rotating slowly to planned pursuit view "
                        f"yaw={planned_entry_yaw_deg:.1f}deg "
                        f"(delta={entry_yaw_delta_deg:+.1f}deg, "
                        f"speed={PLANNER_ENTRY_YAW_SPEED_DEG_S:.1f}deg/s)"
                    )
                    try:
                        heading_result = await rotate_to_yaw_until_target_observed(
                            drone,
                            tracker,
                            planned_entry_yaw_deg,
                            timeout_s=ROTATE_TIMEOUT_S,
                            tolerance_deg=ROTATE_TOLERANCE,
                            max_yaw_speed_deg_s=PLANNER_ENTRY_YAW_SPEED_DEG_S,
                            min_yaw_speed_deg_s=PLANNER_ENTRY_YAW_MIN_SPEED_DEG_S,
                            centered_bearing_deg=PLANNER_ENTRY_YAW_CENTER_BEARING_DEG,
                        )
                    except Exception as exc:
                        await drone.set_velocity(VelocityCommand())
                        set_detection_enabled(False, "planner entry-yaw error")
                        suppress_target_until_lost = True
                        suppress_target_started_at = time.time()
                        route_phase["phase"] = "wall_follow"
                        print(
                            "  [planner] entry-yaw detection failed: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        continue
                    reacquired_observation = heading_result.get("observation")
                    if reacquired_observation is not None:
                        print(
                            "  [planner] target usable during entry yaw "
                            f"yaw={heading_result['yaw_deg']:.1f}deg "
                            f"target={planned_entry_yaw_deg:.1f}deg "
                            f"bearing={heading_result.get('target_bearing_deg', math.nan):+.1f}deg"
                        )
                    elif not heading_result["ok"]:
                        print("  WARNING: planner entry yaw rotation timed out")
                    else:
                        print(
                            "  [planner] planned yaw reached without target; "
                            "waiting for post-yaw frames"
                        )
                else:
                    print("  WARNING: planner entry yaw unavailable; starting pursuit at current heading")

                if reacquired_observation is None:
                    print(
                        "  [planner] waiting for post-yaw target detection "
                        f"({PLANNER_REACQUIRE_TIMEOUT_S:.1f}s)"
                    )
                    reacquired_observation = await wait_for_fresh_target_observation(
                        tracker,
                        timeout_s=PLANNER_REACQUIRE_TIMEOUT_S,
                        centered_bearing_deg=PLANNER_ENTRY_YAW_CENTER_BEARING_DEG,
                    )
                if reacquired_observation is None:
                    set_detection_enabled(False, "planner post-yaw target not usable")
                    suppress_target_until_lost = True
                    suppress_target_started_at = time.time()
                    route_phase["phase"] = "wall_follow"
                    print(
                        "  [planner] not entering pursuit: "
                        "reason=post_yaw_target_not_usable "
                        f"timeout={PLANNER_REACQUIRE_TIMEOUT_S:.1f}s "
                        f"max_bearing={PLANNER_ENTRY_YAW_CENTER_BEARING_DEG:.1f}deg"
                    )
                    continue

                post_yaw_bearing_deg = camera_bearing_deg(reacquired_observation)
                print(
                    "  [planner] post-yaw target usable: "
                    f"conf={reacquired_observation.confidence:.0%} "
                    f"bearing={post_yaw_bearing_deg:+.1f}deg "
                    f"bbox_w={bbox_width_px(reacquired_observation):.0f}px"
                )
                pursuit_entry_point = await record_pose_event(
                    drone,
                    map_events,
                    event_type="pursuit_entry",
                    label=f"Pursuit entry on leg {leg}",
                    leg=leg,
                )
                print(
                    "  Pursuit entry recorded: "
                    f"x={pursuit_entry_point['x']:.2f} y={pursuit_entry_point['y']:.2f} "
                    f"yaw={pursuit_entry_point['yaw_deg']:.1f}"
                )

                final_entry_return_result = None
                final_heading_result = None
                final_pursuit_result = None
                pursuit_success = False

                for attempt in range(1, MAX_PURSUIT_ATTEMPTS + 1):
                    set_detection_enabled(True, f"pursuit attempt {attempt}")
                    pursuit_result = await pursue_and_finish(leg, attempt)
                    final_pursuit_result = pursuit_result
                    set_detection_enabled(False, "return to pursuit entry")

                    if pursuit_result.reached_target:
                        if target_removal_event is not None:
                            removal = remove_nearest_model(
                                world_name=sim_world,
                                x=float(target_removal_event["x"]),
                                y=float(target_removal_event["y"]),
                                env=gz_env,
                                worlds_dir=os.path.join(REPO_ROOT, "worlds"),
                                model_names=None,
                                name_prefixes=target_model_prefixes,
                                uri_keywords=target_uri_keywords,
                                max_distance_m=None,
                            )
                            map_events.append(
                                {
                                    "type": "target_removed",
                                    "label": "Pursued target removed from simulation",
                                    "success": removal.success,
                                    "world": removal.world_name,
                                    "model": removal.model_name,
                                    "distance_m": removal.distance_m,
                                    "target_estimate_x": target_removal_event["x"],
                                    "target_estimate_y": target_removal_event["y"],
                                    "target_local_x": target_removal_event["local_x"],
                                    "target_local_y": target_removal_event["local_y"],
                                    "target_range_m": target_removal_event["range_m"],
                                    "message": removal.message,
                                    "timestamp": time.time(),
                                    "leg": target_removal_event["leg"],
                                }
                            )
                            if removal.success:
                                distance = (
                                    "?"
                                    if removal.distance_m is None
                                    else f"{removal.distance_m:.2f}m"
                                )
                                print(
                                    f"  Removed target model {removal.model_name!r} "
                                    f"from world {removal.world_name!r} "
                                    f"(target_estimate={target_removal_event['x']:.2f},"
                                    f"{target_removal_event['y']:.2f} nearest={distance})"
                                )
                            else:
                                print(f"  WARNING: target removal skipped/failed: {removal.message}")
                        else:
                            print("  WARNING: target removal skipped: PX4/Gazebo frame transform unavailable")

                    await drone.set_velocity(VelocityCommand())
                    returned = await return_to_pursuit_entry(
                        pursuit_entry_point,
                        leg,
                        attempt,
                        pursuit_result.reason,
                    )
                    if returned is None:
                        return
                    final_entry_return_result, final_heading_result = returned

                    if pursuit_result.reached_target:
                        pursuit_success = True
                        break

                    if attempt < MAX_PURSUIT_ATTEMPTS:
                        print(
                            "  Pursuit attempt "
                            f"{attempt}/{MAX_PURSUIT_ATTEMPTS} failed "
                            f"({pursuit_result.reason}); retrying from pursuit entry."
                        )
                    else:
                        print(
                            "  Pursuit failed after "
                            f"{MAX_PURSUIT_ATTEMPTS} attempts ({pursuit_result.reason}); "
                            "resuming leg scan."
                        )
                        suppress_target_until_lost = True
                        suppress_target_started_at = time.time()
                        map_events.append(
                            {
                                "type": "pursuit_failed",
                                "label": f"Pursuit failed on leg {leg}",
                                "x": final_entry_return_result["x"],
                                "y": final_entry_return_result["y"],
                                "yaw_deg": final_heading_result["yaw_deg"],
                                "reason": pursuit_result.reason,
                                "attempts": MAX_PURSUIT_ATTEMPTS,
                                "success": False,
                                "timestamp": time.time(),
                                "leg": leg,
                            }
                        )
                        print("  Failed target will be ignored until it is no longer visible.")

                if final_entry_return_result is None or final_heading_result is None:
                    return

                print("\n--- Phase 7: resume interrupted leg scan ---")
                route_phase["phase"] = "wall_follow"
                map_events.append(
                    {
                        "type": "scan_resumed",
                        "label": f"Resumed scan on leg {leg} after pursuit",
                        "x": final_entry_return_result["x"],
                        "y": final_entry_return_result["y"],
                        "yaw_deg": final_heading_result["yaw_deg"],
                        "pursuit_success": pursuit_success,
                        "pursuit_reason": (
                            None if final_pursuit_result is None else final_pursuit_result.reason
                        ),
                        "timestamp": time.time(),
                        "leg": leg,
                    }
                )
                continue

            if wall_result.reason == "interrupted":
                print(f"  Stopped for safety: {wall_stop_reason}. Landing safely.")
                return

            if wall_result.reason != "front_wall":
                print(f"  Leg did not reach a corner ({wall_result.reason}). Landing safely.")
                return

            set_detection_enabled(False, "corner turn/stabilization")
            route_phase["phase"] = "corner_turn"
            turn_label = "final right turn" if leg == max_legs else "right turn"
            print(f"  Turning {turn_label}...")
            if not await _rotate_relative_simple(drone, lidar, 90.0):
                print("  ERROR: rotation failed. Landing safely.")
                return

            print("  Stabilizing corner...")
            if not await _stabilize_corner(drone, lidar, wall_distance, target_alt):
                print("  WARNING: corner stabilization timed out -- continuing")

            if leg == max_legs:
                print("\n--- Full circuit completed after final turn. Landing safely. ---")
                return
            leg += 1

    finally:
        detector.stop()
        if drone.is_armed:
            try:
                if nav is not None:
                    route_phase["phase"] = "landing"
                    print("\nLanding with lidar hold...")
                    landing_tick = 0

                    def on_landing_status(result) -> None:
                        nonlocal landing_tick
                        landing_tick += 1
                        if result.reason == "descending":
                            if landing_tick % 10 != 0:
                                return
                            agl = "?" if result.final_agl_m is None else f"{result.final_agl_m:.2f}m"
                            print(f"  [landing] descending agl={agl}")
                            return
                        agl = "?" if result.final_agl_m is None else f"{result.final_agl_m:.2f}m"
                        print(
                            f"  [landing] {result.reason} agl={agl} "
                            f"touchdown={result.touchdown_confirmed} disarmed={result.disarmed}"
                        )

                    result = await nav.land_with_lidar_hold(
                        targets=_current_landing_targets(
                            lidar,
                            fallback_wall_distance=wall_distance,
                        ),
                        stabilize_first=False,
                        on_status=on_landing_status,
                    )
                    if not result.disarmed and drone.is_armed:
                        await _safe_land(drone)
                else:
                    await _safe_land(drone)
            except Exception as exc:
                print(f"[SAFETY] landing cleanup failed: {exc}")
                try:
                    await asyncio.wait_for(drone.disarm(), timeout=5.0)
                except Exception:
                    pass
        if route_task is not None:
            route_stop_event.set()
            try:
                await asyncio.wait_for(route_task, timeout=2.0)
            except Exception:
                pass
        if not map_saved and (mapper.active or mapper.points or map_events):
            if map_tasks:
                await asyncio.gather(*map_tasks, return_exceptions=True)
                map_tasks.clear()
            try:
                payload = _build_map_payload(
                    mapper,
                    map_events,
                    route_samples,
                    boundary_override=arena_boundary,
                    wall_distance=wall_distance,
                )
                map_path = _save_map_payload(payload, output_dir)
                annotated_path = MapUnit.annotate_map(map_path, center_origin=True)
                map_saved = True
                print(f"\nMap saved: {map_path}")
                print(f"Annotated map: {annotated_path}")
                print(
                    f"MAP_RESULT:{json.dumps({'map_path': str(annotated_path)})}",
                    flush=True,
                )
            except Exception as exc:
                print(f"  WARNING: map save/annotation failed: {exc}")
        if camera is not None:
            camera.stop()
        if ceiling_sensor is not None:
            ceiling_sensor.stop()
        if lidar is not None:
            lidar.stop()

    print("\nHangar circuit pursuit complete.")


def _cleanup_and_exit(exit_code: int = 0) -> None:
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    os._exit(exit_code)


if __name__ == "__main__":
    try:
        asyncio.run(run())
        _cleanup_and_exit(0)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        _cleanup_and_exit(130)
    except Exception as exc:
        print(f"\n[FLIGHT FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        _cleanup_and_exit(1)
