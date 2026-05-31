#!/usr/bin/env python3
"""Ceiling sample + nearest-corner approach + wall-facing room circuit with YOLO.

Flow:
  1) Take off to 2.5m AGL
  2) Sample upward ceiling rangefinder (store value)
    3) Detect the nearest corner (two closest walls) and move to it
    4) Face the wall and run a clockwise 4-leg circuit (front distance hold)
  5) Land

Usage:
    python3 scripts/flight/ceiling_corner_circuit.py --ceiling-dist 1.5
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import argparse
import asyncio
import json
import math
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from scarecrow.controllers.front_wall_detector import FrontWallDetector
from scarecrow.controllers.rotation import rotate_90
from scarecrow.controllers.wall_follow import VelocityCommand, WallFollowController
from scarecrow.detection.yolo import YoloDetector
from scarecrow.drone import Drone
from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.sensors.rangefinder import GazeboRangefinder


SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5
WALL_DISTANCE = 2.5
LATERAL_SPEED = 0.2
FRONT_KP = 0.35
MAX_FORWARD = 0.25
YAW_KP = 8.0
MAX_YAW_SPEED = 18.0
CONTROL_HZ = 20.0
LEG_TIMEOUT_S = 120.0
CORNER_TIMEOUT_S = 40.0
PRE_CORNER_STABILIZE_S = 2.5
ROTATE_SPEED = 12.0
ROTATE_TOLERANCE = 5.0
ROTATE_TIMEOUT_S = 25.0
RIGHT_STOP_TOL = 0.15
RIGHT_STOP_CONFIRM = 6
MIN_FRONT_DISTANCE = 0.8
YOLO_CONFIDENCE = 0.3
YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ceiling-dist",
        type=float,
        default=1.5,
        help="Ceiling distance parameter to store (meters).",
    )
    return parser.parse_args()


def _clamp(val: float, lo: float, hi: float) -> float:
    """Clamp a value to the provided range."""
    return max(lo, min(hi, val))


def _nearest_corner_pair(scan) -> tuple[str, str]:
    """Return the nearest adjacent wall pair from a scan."""
    distances = {
        "front": scan.front_distance(),
        "left": scan.left_distance(),
        "right": scan.right_distance(),
        "rear": scan.rear_distance(),
    }
    pairs = [
        ("front", "left"),
        ("front", "right"),
        ("rear", "left"),
        ("rear", "right"),
    ]
    best_pair = None
    best_sum = float("inf")
    for a, b in pairs:
        da = distances[a]
        db = distances[b]
        if not math.isfinite(da) or not math.isfinite(db):
            continue
        if da + db < best_sum:
            best_sum = da + db
            best_pair = (a, b)
    if best_pair is None:
        nearest = min(distances, key=distances.get)
        if nearest in ("front", "rear"):
            side = "right" if distances["right"] <= distances["left"] else "left"
            return (nearest, side)
        front = "front" if distances["front"] <= distances["rear"] else "rear"
        return (nearest, front)
    return best_pair


def _face_wall_for_corner(pair: tuple[str, str]) -> str:
    """Pick which wall to face so the other is on the right."""
    a, b = pair
    if "right" in pair:
        return b if a == "right" else a
    return "left"


def _rotation_for_corner(pair: tuple[str, str]) -> float:
    """Return a relative yaw rotation (deg) to face the scan direction."""
    if pair == ("rear", "right"):
        return -90.0
    if pair == ("rear", "left"):
        return 0.0
    if pair == ("front", "right"):
        return 90.0
    if pair == ("front", "left"):
        return 180.0
    if "rear" in pair and "right" in pair:
        return -90.0
    if "rear" in pair and "left" in pair:
        return 0.0
    if "front" in pair and "right" in pair:
        return 90.0
    return 180.0


def _normalize_angle(deg: float) -> float:
    """Normalize an angle to the -180..180 range."""
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg


async def _rotate_relative_simple(
    drone: Drone,
    degrees: float,
    speed_deg_s: float = ROTATE_SPEED,
    tolerance_deg: float = ROTATE_TOLERANCE,
    timeout_s: float = ROTATE_TIMEOUT_S,
) -> bool:
    """Rotate by a relative angle using slow compass-only yaw control."""
    await drone.set_velocity(VelocityCommand())
    await asyncio.sleep(0.2)
    start_yaw = await drone.get_yaw()
    target_yaw = _normalize_angle(start_yaw + degrees)
    started = time.time()
    stable_hits = 0
    while time.time() - started < timeout_s:
        current_yaw = await drone.get_yaw()
        error = _normalize_angle(target_yaw - current_yaw)
        if abs(error) <= tolerance_deg:
            stable_hits += 1
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.15)
            if stable_hits >= 3:
                return True
            continue

        stable_hits = 0
        yaw_cmd = _clamp(error * 0.8, -speed_deg_s, speed_deg_s)
        if abs(yaw_cmd) < 3.0:
            yaw_cmd = 3.0 if yaw_cmd >= 0 else -3.0
        await drone.set_velocity(VelocityCommand(yawspeed_deg_s=yaw_cmd))
        await asyncio.sleep(0.08)

    await drone.set_velocity(VelocityCommand())
    return False


async def _rotate_to_face(drone: Drone, lidar: GazeboLidar, direction: str) -> bool:
    """Rotate the drone to face the requested direction."""
    if direction == "front":
        return True
    if direction == "right":
        return await _rotate_relative_simple(drone, 90.0)
    if direction == "left":
        return await _rotate_relative_simple(drone, -90.0)
    if direction == "rear":
        return await _rotate_relative_simple(drone, 180.0)
    return False


async def _stabilize_corner(drone: Drone, lidar: GazeboLidar, timeout_s: float) -> bool:
    """Move until front and left distances match the target."""
    targets = DistanceTargets(front=WALL_DISTANCE, left=WALL_DISTANCE)
    stabilizer = DistanceStabilizerController(
        targets=targets,
        max_forward_speed=0.30,
        max_lateral_speed=0.30,
        tolerance=0.15,
        stable_time=1.0,
    )
    start = time.time()
    while time.time() - start < timeout_s:
        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue
        cmd = stabilizer.update(scan)
        await drone.set_velocity(cmd)
        if stabilizer.done:
            await drone.set_velocity(VelocityCommand())
            return True
        await asyncio.sleep(0.05)
    await drone.set_velocity(VelocityCommand())
    return False


async def _wait_for_rangefinder(rangefinder: GazeboRangefinder, timeout_s: float = 10.0) -> bool:
    """Wait until the rangefinder produces data."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if rangefinder.get_distance_m() is not None:
            return True
        await asyncio.sleep(0.1)
    return False


def _save_ceiling_sample(output_dir: str, ceiling_dist_param: float, measurement: float | None,
                          topic: str | None) -> str:
    """Persist a single ceiling measurement payload."""
    payload = {
        "timestamp": time.time(),
        "ceiling_dist_param": ceiling_dist_param,
        "ceiling_distance_m": measurement,
        "rangefinder_topic": topic,
    }
    out_path = os.path.join(output_dir, "ceiling_measurement.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return out_path


async def _run_leg(drone: Drone, lidar: GazeboLidar, leg_idx: int) -> bool:
    """Run one wall-facing circuit leg."""
    step = 0
    start = time.time()
    controller = WallFollowController(
        side="left",
        target_distance=WALL_DISTANCE,
        forward_speed=MAX_FORWARD,
        front_stop_distance=WALL_DISTANCE,
        max_lateral_speed=0.3,
        min_safe_distance=MIN_FRONT_DISTANCE,
    )
    front_detector = FrontWallDetector(stop_distance_m=WALL_DISTANCE)

    while time.time() - start < LEG_TIMEOUT_S:
        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue

        left_dist = scan.left_distance()
        front_dist = scan.front_distance()
        front_state = front_detector.update(scan)
        cmd = controller.update(
            left_dist,
            front_state.robust_front_m,
            front_wall_confirmed=front_state.front_wall_visible,
            front_stop_reached=front_state.stop_confirmed,
        )
        await drone.set_velocity(cmd)

        if controller.done:
            await drone.set_velocity(VelocityCommand())
            return True

        if step % 20 == 0:
            elapsed = time.time() - start
            print(
                f"  [leg {leg_idx}] {elapsed:5.1f}s front={front_dist:.2f}m "
                f"left={left_dist:.2f}m fwd={cmd.forward_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f}"
            )

        step += 1
        await asyncio.sleep(1.0 / CONTROL_HZ)

    await drone.set_velocity(VelocityCommand())
    return False


async def run() -> None:
    """Run the full ceiling-corner circuit mission."""
    args = parse_args()
    ceiling_dist_param = float(args.ceiling_dist)

    flight_id = f"local_{int(time.time())}"
    output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nFlight ID: {flight_id} (auto)")
    print(f"Output:    {output_dir}")

    # Kill stale MAVSDK servers from previous runs
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

    # --- Parallel warmup: YOLO model + Gazebo topic list in background ---
    detector = YoloDetector(
        model_path=YOLO_MODEL_PATH,
        output_dir=output_dir,
        confidence=YOLO_CONFIDENCE,
        min_interval=1.0,
    )
    yolo_thread = detector.preload_async()
    gz_thread, gz_result = prefetch_gz_env_async()

    # --- Connect drone ---
    drone = Drone(system_address=SYSTEM_ADDRESS)
    print("\nConnecting to drone...")
    if not await drone.connect():
        print("ERROR: could not connect to drone")
        return
    print("Connected.")

    # GPS-denied mode needs the EKF origin established before health checks.
    await drone.set_ekf_origin()

    print("Waiting for position estimate...")
    if not await drone.wait_for_health():
        print("ERROR: position estimate timed out")
        return
    print("Position OK.")

    if not await drone.verify_gps_denied_params(verbose=True):
        print("Sensor config mismatch -- aborting")
        return

    # --- Wait for warmup threads ---
    yolo_thread.join(timeout=30)
    gz_thread.join(timeout=10)
    gz_env = gz_result.env or {}
    topics = gz_result.topics

    # --- Start lidar ---
    print("\nStarting lidar...")
    lidar = GazeboLidar(env=gz_env, num_threads=3)
    lidar._topic = lidar._discover_topic(topic_list=topics)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for _ in range(30):
        await asyncio.sleep(0.1)
        scan = lidar.get_scan()
        if scan is not None:
            print(
                f"  Lidar ready: front={scan.front_distance():.1f}m "
                f"left={scan.left_distance():.1f}m right={scan.right_distance():.1f}m"
            )
            break
    else:
        print("ERROR: no lidar data -- aborting")
        lidar.stop()
        return

    # --- Start camera (wired to YOLO via on_frame callback) ---
    cam_topic = next(
        (
            l.strip() for l in topics.split("\n")
            if "camera_link/sensor/camera/image" in l and "/model/holybro_x500" in l
        ),
        None,
    )
    if cam_topic is None:
        print("ERROR: drone camera topic not found (expected /model/holybro_x500.../camera/image)")
        lidar.stop()
        return
    camera = GazeboCamera(topic=cam_topic, env=gz_env)
    camera.on_frame = detector.process_frame
    camera.start()
    print(f"  Camera topic: {camera.topic}")

    # --- Start ceiling rangefinder ---
    rangefinder = GazeboRangefinder(env=gz_env)
    rangefinder.start()

    # --- Takeoff ---
    print(f"\n--- Takeoff to {TARGET_ALT}m ---")
    await drone.prepare_takeoff(TARGET_ALT)
    await drone.arm()
    print("  Armed!")
    if not await drone.takeoff(TARGET_ALT):
        print("  ERROR: Failed to reach altitude")
        await drone.disarm()
        lidar.stop()
        rangefinder.stop()
        return

    # --- Stabilize hover ---
    print("\n--- Stabilizing ---")
    await asyncio.sleep(PRE_CORNER_STABILIZE_S)

    # --- Ceiling measurement ---
    print("\n--- Sampling ceiling distance ---")
    if not await _wait_for_rangefinder(rangefinder, timeout_s=10.0):
        print("  WARNING: No ceiling rangefinder data")
        sample = None
    else:
        sample = rangefinder.get_distance_m()
        print(f"  Ceiling distance: {sample:.2f}m")

    sample_path = _save_ceiling_sample(
        output_dir,
        ceiling_dist_param=ceiling_dist_param,
        measurement=sample,
        topic=rangefinder.topic,
    )
    print(f"  Saved: {sample_path}")

    # --- Start offboard control ---
    if not await drone.start_offboard():
        print("ERROR: offboard start failed")
        await drone.disarm()
        lidar.stop()
        rangefinder.stop()
        camera.stop()
        detector.stop()
        return
    print("Offboard mode active")

    # --- Find nearest corner without turning ---
    scan = lidar.get_scan()
    if scan is None:
        print("ERROR: no lidar scan for corner approach")
        await drone.emergency_land()
        lidar.stop()
        rangefinder.stop()
        camera.stop()
        detector.stop()
        return

    corner_pair = _nearest_corner_pair(scan)
    print(f"\n--- Nearest corner (no turn): {corner_pair[0]} + {corner_pair[1]} ---")

    print("\n--- Moving to nearest corner (lidar targets) ---")
    targets = DistanceTargets(
        front=WALL_DISTANCE if "front" in corner_pair else None,
        rear=WALL_DISTANCE if "rear" in corner_pair else None,
        left=WALL_DISTANCE if "left" in corner_pair else None,
        right=WALL_DISTANCE if "right" in corner_pair else None,
    )
    stabilizer = DistanceStabilizerController(
        targets=targets,
        max_forward_speed=0.35,
        max_lateral_speed=0.3,
        tolerance=0.15,
        stable_time=1.2,
    )
    start = time.time()
    step = 0
    while time.time() - start < CORNER_TIMEOUT_S:
        scan = lidar.get_scan()
        if scan is None:
            await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
            continue
        cmd = stabilizer.update(scan)
        await drone.set_velocity(cmd)
        if step % 10 == 0:
            print(
                f"  [corner] front={scan.front_distance():.2f}m "
                f"rear={scan.rear_distance():.2f}m "
                f"left={scan.left_distance():.2f}m "
                f"right={scan.right_distance():.2f}m"
            )
        if stabilizer.done:
            await drone.set_velocity(VelocityCommand())
            break
        step += 1
        await asyncio.sleep(0.05)
    else:
        print("  WARNING: corner stabilization timed out")

    print("\n--- Aligning for circuit ---")
    rotate_deg = _rotation_for_corner(corner_pair)
    if abs(rotate_deg) > 1.0:
        ok = await _rotate_relative_simple(drone, rotate_deg)
        if not ok:
            print("ERROR: rotation failed")
            await drone.emergency_land()
            lidar.stop()
            rangefinder.stop()
            camera.stop()
            detector.stop()
            return

    print("\n--- Start detection (face wall) ---")
    detector.start()

    # --- Circuit ---
    print("\n--- Starting clockwise circuit (face wall) ---")
    for leg in range(1, 5):
        print(f"\n--- Leg {leg}/4 ---")
        ok = await _run_leg(drone, lidar, leg)
        if not ok:
            print("  WARNING: leg ended early")
            break

        print("  Turning right...")
        ok = await _rotate_relative_simple(drone, 90.0)
        if not ok:
            print("  ERROR: rotation failed")
            break

        print("  Stabilizing corner...")
        await _stabilize_corner(drone, lidar, timeout_s=CORNER_TIMEOUT_S)

    # --- Land ---
    print("\n--- Landing ---")
    await drone.stop_offboard()
    await drone.land()
    await asyncio.sleep(1.0)
    await drone.disarm()

    camera.stop()
    detector.stop()
    lidar.stop()
    rangefinder.stop()

    print("\n=== CEILING CORNER CIRCUIT COMPLETE ===")


if __name__ == "__main__":
    asyncio.run(run())