#!/usr/bin/env python3
"""Wall-follow mission that interrupts into pigeon pursuit.

Run with Gazebo already launched, usually:
    ./scripts/shell/launch_with_stream.sh hangar_1_wall_pursuit --fixed --center
    .venv/bin/python scripts/flight/wall_follow_pigeon_pursuit.py --ceiling-clearance 1.0
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import subprocess
import sys
import time

os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.controllers.distance_stabilizer import DistanceTargets
from scarecrow.controllers.target_pursuit import TargetPursuitConfig, TargetPursuitResult
from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.detection.tracking import TargetTracker
from scarecrow.detection.yolo import YoloDetector
from scarecrow.drone import Drone
from scarecrow.navigation.navigation_unit import NavigationUnit
from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.sensors.rangefinder import GazeboRangefinder


SYSTEM_ADDRESS = "udp://:14540"
DEFAULT_TARGET_ALT = 2.5
DEFAULT_TARGET_DIST = 1.5
DEFAULT_WALL_DISTANCE = 3.0
DEFAULT_HOVER_SECONDS = 5.0
DEFAULT_WALL_TIMEOUT = 300.0
DEFAULT_IMAGE_WIDTH = 1280
YOLO_CONFIDENCE = 0.3
YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")

# Match the tuned wall-follow behavior used by room_circuit_map.py.
WALL_FOLLOW_SPEED = 0.30
WALL_FOLLOW_KP = 0.75
WALL_FOLLOW_KD = 0.22
WALL_FOLLOW_MAX_LATERAL = 0.24
WALL_FOLLOW_YAW_KP = 2.0
WALL_FOLLOW_MAX_YAW = 8.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Follow the left wall, pursue pigeon on detection, then land."
    )
    parser.add_argument("--flight-id", default=None)
    parser.add_argument("--system-address", default=SYSTEM_ADDRESS)
    parser.add_argument("--target-alt", type=float, default=DEFAULT_TARGET_ALT)
    parser.add_argument(
        "--ceiling-clearance",
        type=float,
        default=None,
        help="Optional minimum safe upward ceiling clearance in meters.",
    )
    parser.add_argument("--target-dist", type=float, default=DEFAULT_TARGET_DIST)
    parser.add_argument("--wall-distance", type=float, default=DEFAULT_WALL_DISTANCE)
    parser.add_argument("--hover-seconds", type=float, default=DEFAULT_HOVER_SECONDS)
    parser.add_argument(
        "--wall-timeout",
        type=float,
        default=DEFAULT_WALL_TIMEOUT,
        help="Maximum real-time seconds to wall-follow before landing safely.",
    )
    parser.add_argument("--pursuit-timeout", type=float, default=45.0)
    return parser.parse_args()


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


def _fmt_m(value: float | None, precision: int = 1) -> str:
    if value is None or not math.isfinite(value):
        return "inf"
    return f"{value:.{precision}f}m"


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
    flight_id = args.flight_id or f"wall_pursuit_{int(time.time())}"
    output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
    os.makedirs(output_dir, exist_ok=True)

    print("\n" + "=" * 62)
    print("  SCARECROW DRONE - WALL FOLLOW PIGEON PURSUIT")
    print("=" * 62)
    print(f"Flight ID:         {flight_id}")
    print(f"Output:            {output_dir}")
    print(f"Takeoff altitude:  {args.target_alt:.2f}m AGL")
    print(f"Wall distance:     {args.wall_distance:.2f}m")
    print(f"Target distance:   {args.target_dist:.2f}m")
    if args.ceiling_clearance is not None:
        print(f"Min ceiling clear: {args.ceiling_clearance:.2f}m")

    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

    tracker = TargetTracker(image_width=DEFAULT_IMAGE_WIDTH)
    detector = YoloDetector(
        model_path=YOLO_MODEL_PATH,
        output_dir=output_dir,
        confidence=YOLO_CONFIDENCE,
        on_detection_data=tracker.update_from_yolo,
    )
    yolo_thread = detector.preload_async()
    gz_thread, gz_result = prefetch_gz_env_async()

    drone = Drone(system_address=args.system_address)
    lidar: GazeboLidar | None = None
    camera: GazeboCamera | None = None
    ceiling_sensor: GazeboRangefinder | None = None

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

        print("\nStarting 2D lidar...")
        lidar = GazeboLidar(env=gz_env, num_threads=3)
        lidar._topic = lidar._discover_topic(topic_list=topics)
        lidar.start()
        print(f"  Lidar topic: {lidar.topic}")

        if args.ceiling_clearance is not None:
            print("Starting upward ceiling rangefinder...")
            ceiling_sensor = GazeboRangefinder(env=gz_env)
            ceiling_sensor._topic = ceiling_sensor._discover_topic(topic_list=topics)
            ceiling_sensor.start()
            print(f"  Ceiling topic: {ceiling_sensor.topic}")

        for _ in range(30):
            await asyncio.sleep(0.1)
            scan = lidar.get_scan()
            if scan is not None:
                print(
                    f"  Lidar ready: rear={scan.rear_distance():.1f}m  "
                    f"left={scan.left_distance():.1f}m  "
                    f"front={scan.front_distance():.1f}m"
                )
                break
        else:
            print("ERROR: no lidar data -- aborting")
            return

        cam_topic = _find_drone_camera_topic(topics)
        if cam_topic is None:
            print("ERROR: drone camera topic not found")
            return
        camera = GazeboCamera(topic=cam_topic, env=gz_env)
        camera.on_frame = detector.process_frame
        camera.start()
        camera.start_recording(output_dir)
        print(f"  Camera topic: {camera.topic}")

        nav = NavigationUnit(drone, lidar)
        targets = DistanceTargets(rear=args.wall_distance, left=args.wall_distance)

        print(f"\nSetting takeoff altitude to {args.target_alt:.2f}m...")
        await drone.prepare_takeoff(args.target_alt)

        print("Arming...")
        await drone.arm()
        print("Armed.")

        print(f"Taking off to {args.target_alt:.2f}m...")
        if not await drone.takeoff(altitude=args.target_alt):
            print("ERROR: takeoff failed")
            return

        if not await drone.start_offboard():
            print("ERROR: offboard start failed")
            return

        print("\n--- Phase 1: stabilize at takeoff position ---")
        await nav.stabilize(targets, label="wall-pursuit-takeoff")

        if args.ceiling_clearance is not None:
            print("\n--- Phase 2: ceiling safety check ---")
            result = nav.check_ceiling_clearance(
                ceiling_sensor=ceiling_sensor,
                min_clearance_m=args.ceiling_clearance,
            )
            if not result.done:
                print(f"  Ceiling safety check failed: {result.reason}")
                return
            print(f"  Ceiling clearance safe: {result.clearance_m:.2f}m")

        print("\n--- Phase 3: follow left wall and watch for pigeon ---")
        detector.start()

        wall_stop_reason = "target_detected"
        wall_status_tick = 0

        def pigeon_seen() -> bool:
            nonlocal wall_stop_reason
            if tracker.latest(max_age_s=1.5) is not None:
                wall_stop_reason = "target_detected"
                return True
            if args.ceiling_clearance is not None:
                result = nav.check_ceiling_clearance(
                    ceiling_sensor=ceiling_sensor,
                    min_clearance_m=args.ceiling_clearance,
                )
                if not result.done:
                    wall_stop_reason = result.reason
                    return True
            return False

        def on_wall_status(result) -> None:
            nonlocal wall_status_tick
            wall_status_tick += 1
            if wall_status_tick % 10 != 0 and not result.done:
                return
            cmd = result.command or VelocityCommand()
            print(
                f"  [{result.elapsed_s:5.1f}s] fwd={cmd.forward_m_s:+.2f} "
                f"lat={cmd.right_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f} | "
                f"left={_fmt_m(result.wall_distance_m)} "
                f"front={_fmt_m(result.front_distance_m)} "
                f"raw_front={_fmt_m(result.raw_front_distance_m)} "
                f"visible={result.front_wall_visible}"
            )

        wall_result = await nav.wall_follow_until(
            side="left",
            target_distance=args.wall_distance,
            forward_speed=WALL_FOLLOW_SPEED,
            front_stop_distance=args.wall_distance,
            timeout=args.wall_timeout,
            stop_condition=pigeon_seen,
            on_status=on_wall_status,
            kp=WALL_FOLLOW_KP,
            kd=WALL_FOLLOW_KD,
            max_lateral_speed=WALL_FOLLOW_MAX_LATERAL,
            yaw_kp=WALL_FOLLOW_YAW_KP,
            max_yaw_speed=WALL_FOLLOW_MAX_YAW,
        )
        print(
            f"  Wall follow ended: {wall_result.reason} "
            f"(left={_fmt_m(wall_result.wall_distance_m)}, "
            f"front={_fmt_m(wall_result.front_distance_m)}, "
            f"raw_front={_fmt_m(wall_result.raw_front_distance_m)})"
        )

        if wall_result.reason == "interrupted" and wall_stop_reason != "target_detected":
            print(f"  Stopped for ceiling safety: {wall_stop_reason}. Landing safely.")
            return

        if wall_result.reason != "interrupted":
            print("  No pigeon found before wall stop. Landing safely.")
            return

        print(f"\n--- Phase 4: pursue pigeon to {args.target_dist:.2f}m ---")

        def on_pursuit_status(result: TargetPursuitResult) -> None:
            if int(result.elapsed_s * 10) % 20 != 0:
                return
            front = "?" if result.front_distance_m is None else f"{result.front_distance_m:.2f}m"
            age = "?" if result.target_age_s is None else f"{result.target_age_s:.1f}s"
            center = (
                "?"
                if result.center_error_ratio is None
                else f"{result.center_error_ratio:.2f}"
            )
            print(
                f"  [{result.elapsed_s:5.1f}s] {result.state.value} "
                f"front={front} age={age} center_err={center} "
                f"yaw={result.command.yawspeed_deg_s:+.1f} reason={result.reason}"
            )

        pursuit_result = await nav.pursue_target(
            tracker=tracker,
            config=TargetPursuitConfig(
                target_distance_m=args.target_dist,
                pursuit_timeout_s=args.pursuit_timeout,
            ),
            on_status=on_pursuit_status,
        )

        if not pursuit_result.reached_target:
            print(f"  Pursuit ended without reaching target: {pursuit_result.reason}")
            return

        print(
            "  Target reached at "
            f"{pursuit_result.front_distance_m:.2f}m. "
            f"Hovering {args.hover_seconds:.1f}s."
        )
        await nav.hover(args.hover_seconds)

    finally:
        detector.stop()
        if drone.is_armed:
            try:
                await _safe_land(drone)
            except Exception as exc:
                print(f"[SAFETY] landing cleanup failed: {exc}")
                try:
                    await asyncio.wait_for(drone.disarm(), timeout=5.0)
                except Exception:
                    pass
        if lidar is not None:
            lidar.stop()
        if ceiling_sensor is not None:
            ceiling_sensor.stop()
        if camera is not None:
            camera.stop_recording()
            camera.stop()
            print("\nBuilding video...")
            video_path = camera.save_video()
            if video_path:
                print(f"VIDEO_PATH:{video_path}", flush=True)

    print("\nWall-follow pigeon pursuit complete.")


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
