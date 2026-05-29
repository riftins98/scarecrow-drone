#!/usr/bin/env python3
"""Scarecrow Drone pursuit flight -- detect pigeon then approach to 1.5m.

Extends demo_flight_v2.py with a pigeon pursuit phase:
  - Connect via MAVSDK, verify GPS-denied params
  - Takeoff to 2.5m, stabilize at spawn position using lidar walls
  - Hover with YOLO pigeon detection
  - On first detection → pursue pigeon using lidar (range) + YOLO (yaw)
  - Stop at 1.5m front distance, hold position with detection active
  - Lidar-locked descent + disarm
  - Build MP4 video from captured camera frames

Phase overview:
  HOVERING  → (detection) → PURSUING → (front≤1.5m) → HOLDING → land

Usage:
    python3 scripts/flight/demo_flight_pursuit.py [--flight-id abc123]
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

from mavsdk.offboard import VelocityBodyYawspeed

from scarecrow.controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from scarecrow.controllers.target_pursuit import (
    TargetPursuitConfig,
    TargetPursuitResult,
    TargetPursuitState,
)
from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.detection.tracking import TargetTracker
from scarecrow.detection.yolo import YoloDetector
from scarecrow.drone import Drone
from scarecrow.flight.helpers import log_position
from scarecrow.flight.stabilization import lidar_stabilize
from scarecrow.navigation.navigation_unit import NavigationUnit
from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar


# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
DEFAULT_TARGET_ALT = 2.5
HOVER_DURATION = 5
YOLO_CONFIDENCE = 0.3

# Stabilization targets for drone_garage world at spawn (5, -4.5)
# Facing north: front blocked by pigeon billboard, use rear/right instead.
LIDAR_TARGET_REAR = 17.0
LIDAR_TARGET_RIGHT = 3.0

YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")

# --- Pursuit configuration ---
TARGET_DISTANCE = 1.5       # meters — stop when front lidar reads this
MAX_PURSUIT_SPEED = 0.4    # m/s max forward speed during pursuit
MIN_PURSUIT_SPEED = 0.05    # m/s minimum -- prevents near-stop crawling at end
KP_FORWARD = 0.3            # proportional gain: forward_speed = KP * (front - target)
YAW_KP = 15.0               # deg/s per unit of normalized pixel offset
MAX_YAW_SPEED = 20.0        # deg/s clamp
PURSUIT_TIMEOUT = 45.0      # seconds before giving up pursuit
HOLD_DURATION = 5.0          # seconds to hover at target before landing
MIN_WALL_DISTANCE = 0.8     # safety: abort if any wall closer than this
IMAGE_WIDTH = 1280           # camera resolution width for centering calc
CENTER_ENTER_RATIO = 0.05      # must be inside this to enter APPROACHING
CENTER_EXIT_RATIO = 0.08       # leave APPROACHING only if outside this (hysteresis)
DETECTION_MISS_TIMEOUT = 1.8   # tolerant to YOLO jitter
DETECTION_MISS_COUNT_REQUIRED = 2
SEARCH_RIGHT_DEG = 25.0
SEARCH_LEFT_DEG = 50.0
SEARCH_YAW_SPEED = 25.0        # deg/s
RETURN_TO_START_TIMEOUT = 35.0
RETURN_TO_START_TOLERANCE = 0.35
RETURN_STABLE_TIME = 1.2
RETURN_KP = 0.35
RETURN_MAX_SPEED = 0.35


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flight-id", type=str, default=None,
                        help="Flight ID from webapp (optional; auto-generated if omitted)")
    parser.add_argument("--target-alt", type=float, default=DEFAULT_TARGET_ALT,
                        help="Target takeoff altitude in meters AGL (default: 2.5)")
    parser.add_argument("--target-dist", type=float, default=TARGET_DISTANCE,
                        help="Target approach distance to pigeon in meters (default: 1.5)")
    return parser.parse_args()


def emit_telemetry(detector: YoloDetector, distance: float, battery: float = 100.0,
                   phase: str = ""):
    """Print a TELEMETRY: line for webapp parsing."""
    payload = {
        "battery": round(battery, 1),
        "distance": round(distance, 2),
        "detections": detector.detections_total,
        "phase": phase,
    }
    print(f"TELEMETRY:{json.dumps(payload)}", flush=True)


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


async def run():
    args = parse_args()
    target_alt = float(args.target_alt)
    target_dist = float(args.target_dist)

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
    log = get_logger("flight.pursuit", run_id=flight_id, prefix="flight")
    log_event(log, "flight_start", flight_id=flight_id, output_dir=output_dir,
              target_alt=target_alt, hover_duration=HOVER_DURATION,
              target_distance=target_dist,
              system_address=SYSTEM_ADDRESS,
              log_file=str(log_run_file_path()))

    # Kill stale MAVSDK servers from previous runs
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    log_event(log, "stale_mavsdk_killed")

    # --- Parallel warmup: YOLO model + Gazebo topic list in background ---
    tracker = TargetTracker(image_width=IMAGE_WIDTH)
    detector = YoloDetector(
        model_path=YOLO_MODEL_PATH,
        output_dir=output_dir,
        confidence=YOLO_CONFIDENCE,
        on_detection_data=tracker.update_from_yolo,
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

    # GPS-denied mode needs the EKF origin established before PX4's health
    # checks can converge reliably.
    await drone.set_ekf_origin()

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
    reached_target = False

    try:
        # --- Preflight (must happen BEFORE arm -- PX4 uses these in preflight checks) ---
        print(f"\nSetting takeoff altitude to {target_alt}m...")
        start_pos = await drone.prepare_takeoff(target_alt)

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

        log_event(log, "phase", phase="takeoff", target_alt=target_alt)
        print(f"Taking off to {target_alt}m...")
        if not await drone.takeoff(altitude=target_alt):
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

        # ====================================================================
        # Phase 2: Hover with detection → Pursue on first detection
        # ====================================================================
        print(f"\nHovering {HOVER_DURATION}s with detection (waiting for pigeon)...")
        detector.start()
        stabilizer = DistanceStabilizerController(targets=targets)

        hover_start = time.time()
        tick = 0
        pursuit_triggered = False
        initial_detections = detector.detections_total

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
                pos = await drone.get_position()
                distance = abs(pos.position.north_m - start_pos.position.north_m) + \
                           abs(pos.position.east_m - start_pos.position.east_m)
                emit_telemetry(detector, distance, phase="HOVERING")
                await log_position(drone.system, f"HOVER  {time.time() - hover_start:.1f}s",
                                   drone.ground_z)

            # Check for new detection → trigger pursuit
            if detector.detections_total > initial_detections:
                pursuit_triggered = True
                print(f"\n  *** PIGEON DETECTED! Transitioning to pursuit ***")
                log_event(log, "pursuit_triggered",
                          detections=detector.detections_total,
                          hover_elapsed=time.time() - hover_start)
                break

        async def return_to_start() -> bool:
            """Drive back to the recorded takeoff N/E before landing."""
            log_event(log, "phase", phase="RETURNING_HOME")
            stable_since = None
            return_start = time.time()

            while time.time() - return_start < RETURN_TO_START_TIMEOUT:
                pos = await drone.get_position()
                n_err = start_pos.position.north_m - pos.position.north_m
                e_err = start_pos.position.east_m - pos.position.east_m
                dist = (n_err ** 2 + e_err ** 2) ** 0.5

                if dist <= RETURN_TO_START_TOLERANCE:
                    if stable_since is None:
                        stable_since = time.time()
                    elif time.time() - stable_since >= RETURN_STABLE_TIME:
                        await drone.set_velocity(VelocityCommand())
                        print(f"  [return] reached start area (err={dist:.2f}m)")
                        return True
                else:
                    stable_since = None

                yaw_deg = await drone.get_yaw()
                yaw_rad = math.radians(yaw_deg)
                fwd = n_err * math.cos(yaw_rad) + e_err * math.sin(yaw_rad)
                right = -n_err * math.sin(yaw_rad) + e_err * math.cos(yaw_rad)
                cmd = VelocityCommand(
                    forward_m_s=_clamp(RETURN_KP * fwd, -RETURN_MAX_SPEED, RETURN_MAX_SPEED),
                    right_m_s=_clamp(RETURN_KP * right, -RETURN_MAX_SPEED, RETURN_MAX_SPEED),
                    down_m_s=0.0,
                    yawspeed_deg_s=0.0,
                )
                await drone.set_velocity(cmd)
                if int((time.time() - return_start) * 2) % 8 == 0:
                    emit_telemetry(detector, dist, phase="RETURNING_HOME")
                await asyncio.sleep(0.1)

            await drone.set_velocity(VelocityCommand())
            print("  [return] timeout before reaching start area")
            log_event(log, "return_to_start_timeout")
            return False

        if not pursuit_triggered:
            print(f"\n  No pigeon detected during hover. Exiting pursuit mode and landing.")
            log_event(log, "pursuit_not_started_no_detection")
            detector.stop()
            await drone.set_velocity(VelocityCommand())
            reached_target = False
        else:
            # ====================================================================
            # Phase 2b: Pigeon Pursuit (align -> approach -> search if lost)
            # ====================================================================
            print(f"\n--- Phase 2: Pigeon Pursuit (target: {target_dist}m) ---")
            log_event(log, "phase", phase="ALIGNING", target_dist=target_dist)

            pursuit_tick = 0
            last_phase = None

            def on_pursuit_status(result: TargetPursuitResult) -> None:
                nonlocal pursuit_tick, last_phase
                phase = result.state.value
                if phase != last_phase:
                    log_event(log, "phase", phase=phase)
                    last_phase = phase
                if result.state == TargetPursuitState.SEARCHING:
                    emit_telemetry(detector, 0.0, phase=phase)
                    print("  [search] target lost -> running search sweep")
                    return
                pursuit_tick += 1
                if pursuit_tick % 20 == 0:
                    front = result.front_distance_m
                    front_str = "?" if front is None else f"{front:.2f}m"
                    age = result.target_age_s
                    age_str = "?" if age is None else f"{age:.1f}s"
                    print(
                        f"  [{result.elapsed_s:5.1f}s] phase={phase:12s} "
                        f"front={front_str} age={age_str}"
                    )

            pursuit_config = TargetPursuitConfig(
                target_distance_m=target_dist,
                max_forward_speed_m_s=MAX_PURSUIT_SPEED,
                min_forward_speed_m_s=MIN_PURSUIT_SPEED,
                kp_forward=KP_FORWARD,
                yaw_kp=YAW_KP,
                max_yaw_speed_deg_s=MAX_YAW_SPEED,
                min_wall_distance_m=MIN_WALL_DISTANCE,
                center_enter_ratio=CENTER_ENTER_RATIO,
                center_exit_ratio=CENTER_EXIT_RATIO,
                detection_miss_timeout_s=DETECTION_MISS_TIMEOUT,
                detection_miss_count_required=DETECTION_MISS_COUNT_REQUIRED,
                pursuit_timeout_s=PURSUIT_TIMEOUT,
                search_right_deg=SEARCH_RIGHT_DEG,
                search_left_deg=SEARCH_LEFT_DEG,
                search_yaw_speed_deg_s=SEARCH_YAW_SPEED,
            )
            result = await nav.pursue_target(
                tracker=tracker,
                config=pursuit_config,
                on_status=on_pursuit_status,
            )
            reached_target = result.reached_target
            if reached_target:
                print(f"\n  *** TARGET REACHED! Front distance: {result.front_distance_m:.2f}m ***")
                log_event(log, "pursuit_target_reached", front_dist=result.front_distance_m)
            else:
                print(f"\n  Pursuit ended: {result.reason}")
                log_event(log, "pursuit_exit_hover", reason=result.reason)

        # ====================================================================
        # Phase 2c: Hold at target
        # ====================================================================
        if reached_target:
            print(f"\n--- Phase 2c: Holding at {target_dist}m for {HOLD_DURATION}s ---")
            log_event(log, "phase", phase="holding")

            hold_start = time.time()
            hold_tick = 0
            while time.time() - hold_start < HOLD_DURATION:
                scan = lidar.get_scan()
                if scan is not None:
                    # Simple proportional hold: maintain front distance at target
                    front_dist = scan.front_distance()
                    dist_error = front_dist - target_dist
                    fwd = min(max(KP_FORWARD * dist_error, -0.1), 0.15)

                    # Gentle yaw tracking to keep pigeon centered
                    observation = tracker.latest(max_age_s=2.0)
                    yaw = 0.0
                    if observation is not None:
                        image_cx = observation.image_width / 2.0
                        yaw_err = (observation.center_x - image_cx) / image_cx
                        yaw = max(-10.0, min(10.0, yaw_err * YAW_KP * 0.5))

                    cmd = VelocityCommand(forward_m_s=fwd, yawspeed_deg_s=yaw)
                    await drone.set_velocity(cmd)
                else:
                    await drone.set_velocity(VelocityCommand())

                hold_tick += 1
                if hold_tick % 40 == 0:
                    elapsed = time.time() - hold_start
                    pos = await drone.get_position()
                    distance = abs(pos.position.north_m - start_pos.position.north_m) + \
                               abs(pos.position.east_m - start_pos.position.east_m)
                    emit_telemetry(detector, distance, phase="HOLDING")
                    scan_now = lidar.get_scan()
                    if scan_now:
                        print(f"  [hold {elapsed:.1f}s] front={scan_now.front_distance():.2f}m  "
                              f"dets={detector.detections_total}")

                await asyncio.sleep(0.05)

        if pursuit_triggered:
            await return_to_start()

        detector.stop()
        print(f"\n  Pursuit complete. Detections: {detector.detections_total}  "
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
                emit_telemetry(detector, distance, phase="COMPLETE")
            except Exception:
                emit_telemetry(detector, 0.0, phase="COMPLETE")

        print("\n" + "=" * 55)
        print(f"  PURSUIT FLIGHT SUMMARY")
        print(f"  Detections: {detector.detections_total}")
        print(f"  Frames:     {detector.frames_processed}")
        print(f"  Target reached: {'YES' if reached_target else 'NO'}")
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
