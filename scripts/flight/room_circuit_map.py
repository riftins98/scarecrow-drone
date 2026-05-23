#!/usr/bin/env python3
"""
Scarecrow Drone — Room Circuit Mapping Flight

Runs a 4-leg wall-follow circuit and records 2D lidar-based room boundaries.
Outputs a JSON map artifact under scarecrow/mapped_env/<datetime>/map.json and
emits MAP_RESULT: on stdout for future webapp parsing.
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import json
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.controllers.front_wall_detector import FrontWallDetector  # noqa: E402
from scarecrow.controllers.rotation import rotate_90 # noqa: E402
from scarecrow.controllers.wall_follow import WallFollowController, VelocityCommand # noqa: E402
from scarecrow.drone import Drone # noqa: E402
from scarecrow.navigation.map_unit import MapUnit # noqa: E402
from scarecrow.sensors.gz_utils import prefetch_gz_env_async # noqa: E402
from scarecrow.sensors.lidar.gazebo import GazeboLidar # noqa: E402

# --- Configuration ---
SYSTEM_ADDRESS = "udpin://0.0.0.0:14540"
TARGET_ALT = 2.5
WALL_DISTANCE = 2.0
FORWARD_SPEED = 0.6
FRONT_STOP_DISTANCE = 2.0
NUM_LEGS = 4
TURN_DIRECTION = "right"
MAX_CIRCUITS = 1
MAP_RECORD_EVERY = 10
OUTPUT_ROOT = Path(REPO_ROOT) / "scarecrow" / "mapped_env"
WALL_FIND_MIN = 0.3
WALL_FIND_MAX = 8.0
WALL_FIND_TIMEOUT_S = 240.0
WALL_FIND_SPEED = 0.5
CORNER_FIND_SPEED = 0.4
MAP_MIN_DIST = 0.2
MAP_MAX_DIST = 20.0


def faster_forward_speed(base_speed: float, multiplier: float = 1.5, max_speed: float = 0.8) -> float:
    """Return a faster constant forward speed with a safety cap."""
    return min(max_speed, base_speed * multiplier)


def _build_map_payload(mapper: MapUnit, output_dir: Path) -> dict:
    result = mapper.finish_mapping()
    boundaries_json = result.get("boundaries", "[]")
    wall_points = result.get("wall_points", [])
    try:
        boundaries = json.loads(boundaries_json)
    except json.JSONDecodeError:
        boundaries = []
    points = [asdict(p) for p in mapper.points]
    payload = {
        "boundaries": boundaries,
        "boundaries_json": boundaries_json,
        "takeoff_point": mapper.takeoff_point,
        "points": points,
        "wall_points": wall_points,
    }
    return payload


def _save_map(payload: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    map_path = output_dir / "map.json"
    map_path.write_text(json.dumps(payload, indent=2))
    return map_path


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


async def _move_until_wall(drone: Drone, lidar: GazeboLidar, *, axis: str, speed: float,
                           min_m: float, max_m: float, timeout_s: float,
                           log_prefix: str = "", log_all: bool = False) -> bool:
    """Move along one axis until the corresponding wall distance is finite and within range."""
    start = time.time()
    last_log = 0.0
    while time.time() - start < timeout_s:
        scan = lidar.get_scan()
        if scan is not None:
            if axis == "right":
                dist = scan.right_distance()
            elif axis == "front":
                dist = scan.front_distance()
            else:
                raise ValueError("axis must be 'right' or 'front'")
            if axis == "front" and not math.isfinite(dist):
                start = time.time()
                dist = None
            if time.time() - last_log >= 1.0:
                last_log = time.time()
                dist_str = "inf" if dist is None else f"{dist:.2f}m"
                if log_all:
                    front = scan.front_distance()
                    left = scan.left_distance()
                    right = scan.right_distance()
                    front_str = "inf" if not math.isfinite(front) else f"{front:.2f}m"
                    left_str = "inf" if not math.isfinite(left) else f"{left:.2f}m"
                    right_str = "inf" if not math.isfinite(right) else f"{right:.2f}m"
                    print(
                        f"  {log_prefix}dist={dist_str} target=({min_m:.2f}-{max_m:.2f}m) "
                        f"front={front_str} left={left_str} right={right_str}"
                    )
                else:
                    print(f"  {log_prefix}dist={dist_str} target=({min_m:.2f}-{max_m:.2f}m)")
            if _valid_distance(dist, min_m=min_m, max_m=max_m):
                await drone.set_velocity(VelocityCommand())
                return True

        if axis == "right":
            cmd = VelocityCommand(right_m_s=abs(speed))
        else:
            cmd = VelocityCommand(forward_m_s=abs(speed))
        await drone.set_velocity(cmd)
        await asyncio.sleep(0.05)

    await drone.set_velocity(VelocityCommand())
    return False


async def run() -> None:
    drone = Drone(system_address=SYSTEM_ADDRESS)
    mapper = MapUnit()
    lidar = None

    print("Connecting to drone...")
    if not await drone.connect():
        print("ERROR: could not connect to drone")
        return
    print("Connected!")

    print("Waiting for position estimate...")
    if not await drone.wait_for_health():
        print("ERROR: position estimate timed out")
        return
    print("Position estimate OK")

    print("\n--- Pre-flight Setup ---")
    await drone.set_ekf_origin()

    print("\n--- Starting Lidar ---")
    gz_thread, gz_result = prefetch_gz_env_async()
    gz_thread.join(timeout=10)
    gz_env = gz_result.env or {}
    topics = gz_result.topics

    lidar = GazeboLidar(env=gz_env, num_threads=3)
    lidar._topic = lidar._discover_topic(topic_list=topics)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for _ in range(20):
        await asyncio.sleep(0.5)
        scan = lidar.get_scan()
        if scan is not None:
            print(f"  Lidar ready: {scan.num_samples} samples")
            print(
                f"  Front: {scan.front_distance():.1f}m  "
                f"Left: {scan.left_distance():.1f}m  Right: {scan.right_distance():.1f}m"
            )
            break
    else:
        print("  ERROR: No lidar data after 10s")
        lidar.stop()
        return

    print(f"\n--- Takeoff to {TARGET_ALT}m ---")
    await drone.prepare_takeoff(TARGET_ALT)
    await drone.arm()
    print("  Armed!")
    if not await drone.takeoff(TARGET_ALT):
        print("  ERROR: Failed to reach altitude")
        await drone.disarm()
        lidar.stop()
        return

    print("\n--- Stabilizing ---")
    await asyncio.sleep(3)
    scan = lidar.get_scan()
    if scan:
        print(
            f"  Front: {scan.front_distance():.1f}m  "
            f"Left: {scan.left_distance():.1f}m  Right: {scan.right_distance():.1f}m"
        )

    # Record takeoff position before the circuit begins
    pos = await drone.get_position()
    mapper.set_takeoff_point(pos.position.north_m, pos.position.east_m)
    print(f"  Takeoff point recorded: ({pos.position.north_m:.2f}, {pos.position.east_m:.2f})")

    print("\n--- Starting Wall Follow ---")
    print(f"  Target: {WALL_DISTANCE}m from left wall, {FORWARD_SPEED} m/s forward")
    print(f"  Stop when: {FRONT_STOP_DISTANCE}m from front wall")

    if not await drone.start_offboard():
        print("  Offboard start failed")
        await drone.disarm()
        lidar.stop()
        return
    print("  Offboard mode active")

    print("\n--- Turn Right (1/2) ---")
    ok = await rotate_90(drone.system, lidar, direction="right")
    if not ok:
        print("  ERROR: Rotation failed")
        await drone.emergency_land()
        if lidar is not None:
            lidar.stop()
        return

    print("\n--- Approach Wall (1/2) ---")
    if not await _move_until_wall(
        drone,
        lidar,
        axis="front",
        speed=CORNER_FIND_SPEED,
        min_m=0.1,
        max_m=2.2,
        timeout_s=WALL_FIND_TIMEOUT_S,
        log_prefix="corner-1: ",
        log_all=True,
    ):
        print("  ERROR: Could not reach wall (1/2)")
        await drone.emergency_land()
        if lidar is not None:
            lidar.stop()
        return

    print("\n--- Turn Right (2/2) ---")
    ok = await rotate_90(drone.system, lidar, direction="right")
    if not ok:
        print("  ERROR: Rotation failed")
        await drone.emergency_land()
        if lidar is not None:
            lidar.stop()
        return

    print("\n--- Approach Wall (2/2) ---")
    if not await _move_until_wall(
        drone,
        lidar,
        axis="front",
        speed=CORNER_FIND_SPEED,
        min_m=0.1,
        max_m=2.2,
        timeout_s=WALL_FIND_TIMEOUT_S,
        log_prefix="corner-2: ",
        log_all=True,
    ):
        print("  ERROR: Could not reach wall (2/2)")
        await drone.emergency_land()
        if lidar is not None:
            lidar.stop()
        return

    print("\n--- Turn Right (start mapping) ---")
    ok = await rotate_90(drone.system, lidar, direction="right")
    if not ok:
        print("  ERROR: Rotation failed")
        await drone.emergency_land()
        if lidar is not None:
            lidar.stop()
        return

    mapper.start_mapping()
    output_dir = OUTPUT_ROOT / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pos = await drone.get_position()
    mapper.record_corner(pos.position.north_m, pos.position.east_m)

    forward_speed = faster_forward_speed(FORWARD_SPEED)
    controller = WallFollowController(
        target_distance=WALL_DISTANCE,
        forward_speed=forward_speed,
        front_stop_distance=FRONT_STOP_DISTANCE,
    )
    front_detector = FrontWallDetector(stop_distance_m=FRONT_STOP_DISTANCE)

    try:
        circuits_done = 0
        while MAX_CIRCUITS == 0 or circuits_done < MAX_CIRCUITS:
            for leg in range(NUM_LEGS):
                controller.reset()
                front_detector.reset()
                step = 0
                start_time = time.time()
                print(f"\n--- Leg {leg + 1}/{NUM_LEGS} (speed={forward_speed:.2f} m/s) ---")

                while not controller.done:
                    scan = lidar.get_scan()
                    if scan is None:
                        await drone.set_velocity(VelocityCommand())
                        await asyncio.sleep(0.05)
                        continue

                    left_dist = scan.left_distance()
                    front_state = front_detector.update(scan)
                    cmd = controller.update(
                        left_dist,
                        front_state.robust_front_m,
                        front_wall_confirmed=front_state.front_wall_visible,
                        front_stop_reached=front_state.stop_confirmed,
                    )

                    await drone.set_velocity(cmd)

                    if step % MAP_RECORD_EVERY == 0 and _scan_valid_for_map(scan):
                        pos = await drone.get_position()
                        yaw_deg = await drone.get_yaw()
                        mapper.record_position(scan, pos.position.north_m, pos.position.east_m, yaw_deg)
                        mapper.record_left_wall_hit(
                            scan,
                            pos.position.north_m,
                            pos.position.east_m,
                            yaw_deg,
                            min_m=MAP_MIN_DIST,
                            max_m=MAP_MAX_DIST,
                        )

                    if step % 10 == 0:
                        elapsed = time.time() - start_time
                        print(
                            f"  [{elapsed:5.1f}s] fwd={cmd.forward_m_s:+.2f} "
                            f"lat={cmd.right_m_s:+.2f} | left={left_dist:.1f}m "
                            f"front={front_state.robust_front_m:.1f}m"
                        )

                    step += 1
                    await asyncio.sleep(0.05)

                scan = lidar.get_scan()
                if _scan_valid_for_map(scan):
                    pos = await drone.get_position()
                    yaw_deg = await drone.get_yaw()
                    mapper.record_position(scan, pos.position.north_m, pos.position.east_m, yaw_deg)
                    mapper.record_left_wall_hit(
                        scan,
                        pos.position.north_m,
                        pos.position.east_m,
                        yaw_deg,
                        min_m=MAP_MIN_DIST,
                        max_m=MAP_MAX_DIST,
                    )

                pos = await drone.get_position()
                mapper.record_corner(pos.position.north_m, pos.position.east_m)

                await drone.set_velocity(VelocityCommand())
                print("  Turning corner...")
                ok = await rotate_90(drone.system, lidar, direction=TURN_DIRECTION)
                if not ok:
                    raise RuntimeError("rotation_failed")
            circuits_done += 1

    except KeyboardInterrupt:
        print("\nEmergency landing (Ctrl+C)...")
        await drone.emergency_land()
    except Exception as e:
        print(f"  Control error: {e}")
    finally:
        payload = _build_map_payload(mapper, output_dir)
        map_path = _save_map(payload, output_dir)
        summary = {
            "boundaries": payload.get("boundaries_json", "[]"),
            "map_path": str(map_path),
            "point_count": len(payload.get("points", [])),
            "wall_point_count": len(payload.get("wall_points", [])),
        }
        print(f"MAP_RESULT:{json.dumps(summary)}", flush=True)

        await drone.stop_offboard()
        await asyncio.sleep(1)
        await drone.land()
        await asyncio.sleep(1)
        await drone.disarm()
        if lidar is not None:
            lidar.stop()

    print("\n--- Mapping Complete ---")
    print(f"  Map: {map_path}")


if __name__ == "__main__":
    asyncio.run(run())
