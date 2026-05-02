#!/usr/bin/env python3
"""Scarecrow Drone detection flight -- refactored to use the layered architecture.

Behavioral parity with `demo_flight.py`:
  - Connect via MAVSDK, verify GPS-denied params
  - Takeoff to 2.5m, stabilize at spawn position using lidar walls
  - Hover with YOLO pigeon detection for HOVER_DURATION
  - Lidar-locked descent + disarm
  - Build MP4 video from captured camera frames

Differences from v1:
  - Uses Drone / NavigationUnit / YoloDetector.preload_async / prefetch_gz_env_async
  - Does NOT create or finalize flight DB records -- webapp owns that via repositories
  - Emits stdout protocol lines (DETECTION_IMAGE:, TELEMETRY:) for webapp parsing
  - ~180 lines vs ~520

Usage:
    python3 scripts/flight/demo_flight_v2.py [--flight-id abc123]
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import argparse
import asyncio
import json
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from mavsdk.offboard import VelocityBodyYawspeed

from scarecrow.controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.detection.yolo import YoloDetector
from scarecrow.drone import Drone
from scarecrow.flight.helpers import get_position, log_position
from scarecrow.flight.stabilization import lidar_stabilize
from scarecrow.navigation.navigation_unit import NavigationUnit
from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar


# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5
HOVER_DURATION = 5
YOLO_CONFIDENCE = 0.3

# Stabilization targets for drone_garage world at spawn (5, -4.5)
# Facing north: front blocked by pigeon billboard, use rear/right instead.
LIDAR_TARGET_REAR = 17.0
LIDAR_TARGET_RIGHT = 3.0

YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flight-id", type=str, default=None,
                        help="Flight ID from webapp (optional; auto-generated if omitted)")
    return parser.parse_args()


def emit_telemetry(detector: YoloDetector, distance: float, battery: float = 100.0):
    """Print a TELEMETRY: line for webapp parsing."""
    payload = {
        "battery": round(battery, 1),
        "distance": round(distance, 2),
        "detections": detector.detections_total,
    }
    print(f"TELEMETRY:{json.dumps(payload)}", flush=True)


async def run():
    args = parse_args()
    if args.flight_id:
        flight_id = args.flight_id
        print(f"\nFlight ID: {flight_id} (from webapp)")
    else:
        flight_id = f"local_{int(time.time())}"
        print(f"\nFlight ID: {flight_id} (auto)")
    output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
    os.makedirs(output_dir, exist_ok=True)


    print(f"Output:    {output_dir}")

    # --- Init structured logger (open per-flight log file early) ---
    from scarecrow.logging_setup import get_logger, log_event, log_run_file_path
    log = get_logger("flight.demo_v2", run_id=flight_id, prefix="flight")
    log_event(log, "flight_start", flight_id=flight_id, output_dir=output_dir,
              target_alt=TARGET_ALT, hover_duration=HOVER_DURATION,
              system_address=SYSTEM_ADDRESS,
              log_file=str(log_run_file_path()))

    # Kill stale MAVSDK servers from previous runs
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    log_event(log, "stale_mavsdk_killed")

    # --- Parallel warmup: YOLO model + Gazebo topic list in background ---
    detector = YoloDetector(
        model_path=YOLO_MODEL_PATH,
        output_dir=output_dir,
        confidence=YOLO_CONFIDENCE,
    )
    yolo_thread = detector.preload_async()
    gz_thread, gz_result = prefetch_gz_env_async()

    # --- Connect drone in parallel ---
    drone = Drone(system_address=SYSTEM_ADDRESS)
    print("\nConnecting to drone...")
    log_event(log, "phase", phase="connect")
    if not await drone.connect():
        log_event(log, "connect_failed_abort")
        print("ERROR: could not connect to drone")
        return
    print("Connected.")

    print("Waiting for position estimate...")
    log_event(log, "phase", phase="wait_health")
    if not await drone.wait_for_health():
        log_event(log, "health_timeout_abort")
        print("ERROR: position estimate timed out (check optical flow + EKF2)")
        return
    print("Position OK.")

    # --- Sensor config verification ---
    print("\n--- Sensor verification ---")
    log_event(log, "phase", phase="verify_params")
    if not await drone.verify_gps_denied_params(verbose=True):
        log_event(log, "verify_params_failed_abort")
        print("Sensor config mismatch -- aborting")
        return

    # --- Wait for warmup threads ---
    yolo_thread.join(timeout=30)
    gz_thread.join(timeout=10)
    gz_env = gz_result.env or {}
    topics = gz_result.topics

    # --- EKF origin ---
    log_event(log, "phase", phase="set_ekf_origin")
    await drone.set_ekf_origin()

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
                f"  Lidar ready: rear={scan.rear_distance():.1f}m  "
                f"right={scan.right_distance():.1f}m  "
                f"front={scan.front_distance():.1f}m  "
                f"left={scan.left_distance():.1f}m"
            )
            break
    else:
        print("ERROR: no lidar data -- aborting")
        lidar.stop()
        return

    # --- Start camera (wired to YOLO via on_frame callback) ---
    cam_topic = next(
        (
            l.strip() for l in topics.split('\n')
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
    camera.start_recording(output_dir)
    print(f"  Camera topic: {camera.topic}")

    nav = NavigationUnit(drone, lidar)
    targets = DistanceTargets(rear=LIDAR_TARGET_REAR, right=LIDAR_TARGET_RIGHT)
    start_pos = None

    try:
        # --- Preflight (must happen BEFORE arm -- PX4 uses these in preflight checks) ---
        print(f"\nSetting takeoff altitude to {TARGET_ALT}m...")
        start_pos = await drone.prepare_takeoff(TARGET_ALT)

        # --- Arm + takeoff ---
        log_event(log, "phase", phase="arm")
        print("Arming...")
        try:
            await drone.arm()
        except Exception as e:
            log_event(log, "arm_aborted", error=str(e), error_type=type(e).__name__)
            print(f"\nERROR: arm failed -- {e}")
            print("If COMMAND_DENIED: set EKF origin manually in pxh> and retry:")
            print("  commander set_ekf_origin 0 0 0")
            return
        print("Armed.")

        log_event(log, "phase", phase="takeoff", target_alt=TARGET_ALT)
        print(f"Taking off to {TARGET_ALT}m...")
        if not await drone.takeoff(altitude=TARGET_ALT):
            log_event(log, "takeoff_aborted")
            print("ERROR: takeoff failed")
            return
        log_event(log, "phase", phase="airborne")

        # --- Offboard + stabilize ---
        if not await drone.start_offboard():
            print("ERROR: offboard start failed")
            return

        print("\n--- Phase 1: stabilize before hover ---")
        await nav.stabilize(targets, label="pre-hover")

        # --- Hover with YOLO running ---
        print(f"\nHovering {HOVER_DURATION}s with detection...")
        detector.start()
        stabilizer = DistanceStabilizerController(targets=targets)

        hover_start = time.time()
        tick = 0
        while time.time() - hover_start < HOVER_DURATION:
            scan = lidar.get_scan()
            if scan is not None:
                cmd = stabilizer.update(scan)
                await drone.set_velocity(cmd)
                if stabilizer.done:
                    stabilizer.reset()
            else:
                await drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)

            tick += 1
            if tick % 20 == 0:
                # Emit telemetry every ~1s
                pos = await drone.get_position()
                distance = abs(pos.position.north_m - start_pos.position.north_m) + \
                           abs(pos.position.east_m - start_pos.position.east_m)
                emit_telemetry(detector, distance)
                await log_position(drone.system, f"HOVER  {time.time() - hover_start:.1f}s",
                                   drone.ground_z)

        detector.stop()
        print(f"\n  Hover complete. Detections: {detector.detections_total}  "
              f"Frames: {detector.frames_processed}")

        # --- Phase 3: re-stabilize before landing ---
        print("\n--- Phase 3: stabilize before landing ---")
        await lidar_stabilize(drone.system, lidar, targets, label="pre-land")

        # --- Phase 4: lidar-locked descent ---
        print("\nDescending with lidar hold...")
        DESCENT_SPEED = 0.3
        LAND_AGL = 0.35
        LAND_TIMEOUT = 30

        stabilizer.reset()
        land_start = time.time()
        step = 0
        last_cmd = VelocityCommand()
        while time.time() - land_start < LAND_TIMEOUT:
            scan = lidar.get_scan()
            if scan is not None:
                last_cmd = stabilizer.update(scan)
                await drone.system.offboard.set_velocity_body(
                    VelocityBodyYawspeed(last_cmd.forward_m_s, last_cmd.right_m_s, DESCENT_SPEED, 0.0)
                )
                if stabilizer.done:
                    stabilizer.reset()
            else:
                await drone.system.offboard.set_velocity_body(
                    VelocityBodyYawspeed(0.0, 0.0, DESCENT_SPEED, 0.0)
                )
            await asyncio.sleep(0.05)
            step += 1
            if step % 10 == 0:
                pos = await drone.get_position()
                agl = -(pos.position.down_m - drone.ground_z)
                scan_now = lidar.get_scan()
                if scan_now is not None:
                    print(f"  [descent] agl={agl:.2f}m  rear={scan_now.rear_distance():.2f}m  "
                          f"right={scan_now.right_distance():.2f}m  "
                          f"cmd: fwd={last_cmd.forward_m_s:+.2f} lat={last_cmd.right_m_s:+.2f}")
                else:
                    print(f"  [descent] agl={agl:.2f}m  (no lidar)")
                if agl < LAND_AGL:
                    print(f"  Near ground ({agl:.2f}m) -- touching down")
                    break

        # Stop offboard mode first, then trigger PX4 auto-land so the drone
        # actually touches down before we disarm. Without the explicit land(),
        # PX4 often stays in position hold at the current (low) altitude and
        # disarm gets rejected because the vehicle is technically still flying.
        await drone.stop_offboard()
        print("Commanding land...")
        try:
            await drone.land()
        except Exception as e:
            print(f"  land() failed: {e}")

        # Wait briefly for PX4 to finalize touchdown before disarm.
        for _ in range(20):   # up to ~4s
            await asyncio.sleep(0.2)
            try:
                pos = await asyncio.wait_for(drone.get_position(), timeout=1.0)
                agl = -(pos.position.down_m - drone.ground_z)
                if agl < 0.15:
                    break
            except Exception:
                break

        print("Disarming...")
        if await drone.disarm():
            print("  Disarmed.")
        else:
            print("  WARNING: drone did not disarm cleanly -- rotors may still be spinning")

    finally:

        # Safety: ensure motors are off even if the flight phase raised.
        # If disarm already succeeded in the try-block, this is a no-op.
        if drone.is_armed:
            print("\n[SAFETY] Drone still armed on cleanup -- forcing disarm/kill")
            try:
                await asyncio.wait_for(drone.disarm(), timeout=5.0)
            except Exception as e:
                print(f"[SAFETY] safety disarm failed: {e}")

        lidar.stop()
        camera.stop_recording()
        camera.stop()

        print("\nBuilding video...")
        video_path = camera.save_video()
        if video_path:
            print(f"VIDEO_PATH:{video_path}", flush=True)

        # Final telemetry snapshot (best-effort -- connection may be dead)
        if start_pos is not None:
            try:
                final_pos = await asyncio.wait_for(drone.get_position(), timeout=2.0)
                distance = abs(final_pos.position.north_m - start_pos.position.north_m) + \
                           abs(final_pos.position.east_m - start_pos.position.east_m)
                emit_telemetry(detector, distance)
            except Exception:
                emit_telemetry(detector, 0.0)

        print("\n" + "=" * 55)
        print(f"  FLIGHT SUMMARY")
        print(f"  Detections: {detector.detections_total}")
        print(f"  Frames:     {detector.frames_processed}")
        print(f"  Flight ID:  {flight_id}")
        print(f"  Output:     {output_dir}/")
        print("=" * 55)


def _cleanup_and_exit(exit_code: int = 0):
    """Ensure mavsdk_server is killed on exit so the next run connects cleanly."""
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    os._exit(exit_code)


if __name__ == "__main__":
    try:
        asyncio.run(run())
        _cleanup_and_exit(0)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        _cleanup_and_exit(130)
    except Exception as e:
        print(f"\n[FLIGHT FAILED] {type(e).__name__}: {e}", file=sys.stderr)
        _cleanup_and_exit(1)
