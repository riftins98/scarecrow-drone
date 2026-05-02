#!/usr/bin/env python3
"""
Scarecrow Drone — Hover Test (MAVSDK)

GPS-denied indoor flight using ONLY:
  - Optical flow (MTF-01) for horizontal velocity
  - Downward rangefinder (TF-Luna) for height
  - 2D lidar (RPLidar A1M8) for obstacle avoidance
  - Mono camera (Pi Camera 3) for visual awareness

Sequence: arm -> takeoff to 2.5m -> stabilize -> hover (with YOLO detection) -> stabilize -> land
Records camera video throughout flight.
Captures lidar scan + optical flow snapshot at hover.
Creates a flight record in the webapp DB — visible in the UI.

This script runs identically on simulation and real hardware.
Only the connection string changes:
  Sim:  udp://:14540
  Real: serial:///dev/ttyACM0:921600
"""

import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import subprocess
import sys
import threading
import time

import argparse
import numpy as np
from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5        # meters above ground
HOVER_DURATION = 5      # seconds to hover for detection
YOLO_CONFIDENCE = 0.3

# Lidar stabilization targets — distances from spawn position (5, -4.5) in drone_garage
# Drone faces north (+x, yaw=0): rear=south wall, right=west wall
# NOTE: front wall blocked by pigeon billboard — use rear instead
LIDAR_TARGET_REAR = 17.0   # meters to south wall
LIDAR_TARGET_RIGHT = 3.0   # meters to west wall

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Webapp DB path
sys.path.insert(0, os.path.join(REPO_ROOT, "webapp", "backend"))
from database.db import create_flight, end_flight

# YOLO model
YOLO_MODEL_PATH = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")

# Scarecrow package
from scarecrow.sensors.gz_utils import get_gz_env
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.sensors.camera.gazebo import GazeboCamera
from scarecrow.controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from scarecrow.detection.yolo import YoloDetector
from scarecrow.flight.helpers import get_position, wait_for_altitude, wait_for_stable, log_position
from scarecrow.flight.stabilization import lidar_stabilize


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--flight-id", type=str, default=None,
                        help="Flight ID from webapp (if omitted, a new one is created)")
    return parser.parse_args()






async def run():
    args = parse_args()

    # --- Kill leftover mavsdk_server from previous runs ---
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

    # --- Flight record in DB ---
    if args.flight_id:
        flight_id = args.flight_id
        print(f"\nFlight ID: {flight_id} (from webapp)")
    else:
        flight_id = create_flight()
        print(f"\nFlight ID: {flight_id} (new)")
    output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output:    {output_dir}")

    # --- Launch background tasks in parallel while connecting ---
    detector = YoloDetector(
        model_path=YOLO_MODEL_PATH,
        output_dir=output_dir,
        confidence=YOLO_CONFIDENCE,
    )
    gz_topics_cache = [None]
    gz_env_cache = [None]

    def prefetch_gz():
        gz_env_cache[0] = get_gz_env()
        try:
            result = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True, text=True, timeout=5, env=gz_env_cache[0]
            )
            gz_topics_cache[0] = result.stdout
        except Exception:
            gz_topics_cache[0] = ""

    yolo_thread = threading.Thread(target=detector.load_model, daemon=True)
    gz_thread = threading.Thread(target=prefetch_gz, daemon=True)
    yolo_thread.start()
    gz_thread.start()

    # --- Connect to drone ---
    drone = System()
    print("\nConnecting to drone...")
    await drone.connect(system_address=SYSTEM_ADDRESS)

    print("Waiting for connection (timeout 30s)...")
    try:
        async with asyncio.timeout(30):
            async for state in drone.core.connection_state():
                if state.is_connected:
                    print("Connected!")
                    break
    except asyncio.TimeoutError:
        print("ERROR: Could not connect to drone. Is PX4 running?")
        end_flight(flight_id, pigeons=0, frames=0)
        return

    print("Waiting for position estimate (timeout 60s)...")
    try:
        async with asyncio.timeout(60):
            async for health in drone.telemetry.health():
                if health.is_local_position_ok:
                    print("Position estimate OK")
                    break
    except asyncio.TimeoutError:
        print("ERROR: Position estimate timed out. Check optical flow + EKF2.")
        end_flight(flight_id, pigeons=0, frames=0)
        return

    # Wait for background tasks if still running
    if yolo_thread.is_alive():
        print("Waiting for YOLO model...")
        yolo_thread.join()
    if gz_thread.is_alive():
        gz_thread.join()

    topics = gz_topics_cache[0] or ""
    gz_env = gz_env_cache[0] or get_gz_env()

    # --- Verify sensor configuration ---
    print("\n" + "=" * 55)
    print("  SENSOR VERIFICATION — GPS-Denied Navigation")
    print("=" * 55)
    params_check = {
        'EKF2_GPS_CTRL':  (0, "GPS disabled"),
        'EKF2_OF_CTRL':   (1, "Optical flow enabled"),
        'SYS_HAS_GPS':    (0, "GPS hardware disabled"),
    }
    all_ok = True
    for name, (expected, desc) in params_check.items():
        val = int(await drone.param.get_param_int(name))
        ok = val == expected
        print(f"  [{'OK' if ok else 'FAIL'}] {name} = {val} -- {desc}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nSensor config mismatch! Aborting.")
        end_flight(flight_id, pigeons=0, frames=0)
        return

    print("\n  All params OK: optical flow + rangefinder navigation")
    print("=" * 55)

    # --- Verify Gazebo sensor topics (using cached result) ---
    print("\n--- Gazebo Sensor Topics ---")
    sensors = {
        "Optical flow (MTF-01)":  "optical_flow/optical_flow",
        "Flow camera":            "flow_camera/image",
        "Downward rangefinder":   "lidar_sensor_link/sensor/lidar/scan",
        "2D lidar (RPLidar)":     "lidar_2d_v2",
        "Mono camera (Pi Cam)":   "camera_link/sensor/camera",
    }
    for name, pattern in sensors.items():
        print(f"  [{'OK' if pattern in topics else 'MISSING'}] {name}")

    # --- Pre-flight Setup ---
    print("\n--- Pre-flight Setup ---")
    try:
        await drone.action.set_gps_global_origin(0.0, 0.0, 0.0)
        print("  EKF origin set (0, 0, 0)")
    except Exception as e:
        print(f"  set_gps_global_origin failed: {e}")

    # --- Start lidar (use cached topic) ---
    print("\nStarting lidar...")
    lidar_topic = next((l.strip() for l in topics.split('\n') if "lidar_2d_v2/scan" in l and "points" not in l), None)
    lidar = GazeboLidar(topic=lidar_topic, env=gz_env, num_threads=3)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for _ in range(30):
        await asyncio.sleep(0.1)
        scan = lidar.get_scan()
        if scan is not None:
            print(f"  Lidar ready: {scan.num_samples} samples")
            print(f"  Rear: {scan.rear_distance():.1f}m  Right: {scan.right_distance():.1f}m  "
                  f"Front: {scan.front_distance():.1f}m  Left: {scan.left_distance():.1f}m")
            print(f"  Stabilization targets: rear={LIDAR_TARGET_REAR}m  right={LIDAR_TARGET_RIGHT}m")
            break
    else:
        print("  ERROR: No lidar data — aborting")
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return

    # --- Read ground position ---
    ground = await get_position(drone)
    ground_z = ground.position.down_m
    print(f"\n--- Flight Sequence ---")
    print(f"  Ground reference: z={ground_z:.3f} (NED)")

    # --- Start camera (use cached topic) ---
    cam_topic = next(
        (
            l.strip() for l in topics.split('\n')
            if "camera_link/sensor/camera/image" in l and "/model/holybro_x500" in l
        ),
        None,
    )
    if cam_topic is None:
        print("  ERROR: Drone camera topic not found (expected /model/holybro_x500.../camera/image)")
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return
    camera = GazeboCamera(topic=cam_topic, env=gz_env)
    camera.on_frame = detector.process_frame
    camera.start()
    camera.start_recording(output_dir)
    if camera.topic:
        print(f"  Camera topic: {camera.topic}")

    # --- Takeoff ---
    print(f"\nSetting takeoff altitude to {TARGET_ALT}m...")
    await drone.action.set_takeoff_altitude(TARGET_ALT)

    print("Arming...")
    await drone.action.arm()
    print("Armed!")

    print(f"Taking off to {TARGET_ALT}m...")
    await drone.action.takeoff()

    if not await wait_for_altitude(drone, TARGET_ALT, ground_z, timeout=30):
        print("ERROR: Failed to reach target altitude. Aborting.")
        camera.stop()
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return

    print(f"\nReached {TARGET_ALT}m — waiting for stable hover...")
    await wait_for_stable(drone, ground_z)

    # --- Enter offboard mode ---
    targets = DistanceTargets(rear=LIDAR_TARGET_REAR, right=LIDAR_TARGET_RIGHT)

    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))
    try:
        await drone.offboard.start()
        print("  Offboard mode active")
    except OffboardError as e:
        print(f"  Offboard start failed: {e} — aborting")
        camera.stop()
        lidar.stop()
        end_flight(flight_id, pigeons=0, frames=0)
        return

    # --- Phase 1: Lidar stabilize to spawn position ---
    print(f"\n--- Phase 1: Lidar Stabilization (rear={LIDAR_TARGET_REAR}m, right={LIDAR_TARGET_RIGHT}m) ---")
    await lidar_stabilize(drone, lidar, targets, label="pre-hover")

    # --- Phase 2: Hover with YOLO detection + lidar hold ---
    print(f"\nHovering at {TARGET_ALT}m for {HOVER_DURATION}s — running pigeon detection...")

    # Start lidar/flow capture in background
    sensor_thread = threading.Thread(target=capture_lidar_and_flow,
                                     args=(output_dir,), daemon=True)
    sensor_thread.start()

    # Detection runs via camera.on_frame callback
    detector.start()

    # Continuous lidar hold during hover
    stabilizer = DistanceStabilizerController(
        targets=targets,
        kp_front_rear=0.40,
        kp_left_right=0.45,
        max_forward_speed=0.25,
        max_lateral_speed=0.25,
        tolerance=0.15,
        stable_time=1.0,
    )

    hover_start = time.time()
    step = 0
    while time.time() - hover_start < HOVER_DURATION:
        scan = lidar.get_scan()
        if scan is not None:
            cmd = stabilizer.update(scan)
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, 0.0, 0.0)
            )
            if stabilizer.done:
                stabilizer.reset()
        else:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0))

        await asyncio.sleep(0.05)
        step += 1
        if step % 20 == 0:
            await log_position(drone, f"HOVER  {time.time() - hover_start:.1f}s", ground_z)

    detector.stop()
    sensor_thread.join(timeout=3)

    print(f"\n  Hover complete. Pigeons detected: {detector.detections_total} "
          f"(frames: {detector.frames_processed})")

    # --- Phase 3: Re-stabilize before landing ---
    print("\n--- Phase 3: Re-stabilize to landing position ---")
    await lidar_stabilize(drone, lidar, targets, label="pre-land")

    # --- Phase 4: Lidar-locked descent ---
    print("\nLanding with lidar position hold...")
    DESCENT_SPEED = 0.3   # m/s downward
    LAND_AGL = 0.35       # meters AGL — disarm below this
    LAND_TIMEOUT = 30     # seconds

    stabilizer.reset()
    land_start = time.time()
    step = 0

    while time.time() - land_start < LAND_TIMEOUT:
        scan = lidar.get_scan()
        if scan is not None:
            cmd = stabilizer.update(scan)
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, DESCENT_SPEED, 0.0)
            )
            if stabilizer.done:
                stabilizer.reset()
        else:
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, DESCENT_SPEED, 0.0)
            )

        await asyncio.sleep(0.05)
        step += 1

        if step % 10 == 0:
            pos = await get_position(drone)
            agl = -(pos.position.down_m - ground_z)
            scan_now = lidar.get_scan()
            if scan_now:
                print(f"  [descent] agl={agl:.2f}m  rear={scan_now.rear_distance():.2f}m  "
                      f"right={scan_now.right_distance():.2f}m  "
                      f"cmd: fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f}")
            else:
                print(f"  [descent] agl={agl:.2f}m  (no lidar)")
            if agl < LAND_AGL:
                print(f"  [descent] Near ground ({agl:.2f}m) — touching down")
                break

    # Stop offboard and disarm
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass

    print("  Disarming...")
    try:
        await drone.action.disarm()
        print("  Disarmed!")
    except Exception:
        try:
            await drone.action.kill()
            print("  Killed motors")
        except Exception:
            pass

    lidar.stop()

    # --- Stop camera + build video ---
    camera.stop_recording()
    camera.stop()
    print("\nBuilding video...")
    video_path = camera.save_video()

    # --- Finalize flight record ---
    end_flight(
        flight_id,
        pigeons=detector.detections_total,
        frames=detector.frames_processed,
        video_path=video_path,
    )
    print(f"\nFlight record saved (ID: {flight_id})")

    print("\n" + "=" * 55)
    print("  FLIGHT COMPLETE")
    print("  Navigation: optical flow + rangefinder (NO GPS)")
    print(f"  Pigeons detected: {detector.detections_total}")
    print(f"  Frames processed: {detector.frames_processed}")
    print(f"  Flight ID: {flight_id} (visible in UI history)")
    print(f"  Outputs in: {output_dir}/")
    print("=" * 55)


def capture_lidar_and_flow(output_dir):
    """Capture lidar scan and optical flow data."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches

    env = get_gz_env()
    os.makedirs(output_dir, exist_ok=True)

    # --- Lidar scan ---
    try:
        result_topics = subprocess.run(
            ["gz", "topic", "-l"], capture_output=True, text=True, timeout=5, env=env
        )
        lidar_topic = next(
            (l.strip() for l in result_topics.stdout.split('\n') if "lidar_2d_v2/scan" in l and "points" not in l),
            None
        )
        if not lidar_topic:
            print("  Lidar topic not found")
            return
        result = subprocess.run(
            ["gz", "topic", "-e", "-n", "1", "-t", lidar_topic],
            capture_output=True, text=True, timeout=5, env=env
        )
        ranges = []
        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('ranges:'):
                try:
                    val = float(line.split(':')[1].strip())
                    if 0 < val < 30:
                        ranges.append(val)
                except ValueError:
                    pass

        if ranges:
            n = len(ranges)
            angles = np.linspace(-2.356195, 2.356195, n)
            world_x = np.array(ranges) * np.cos(angles)
            world_y = np.array(ranges) * np.sin(angles)
            x = -world_y
            y = world_x

            fig, ax = plt.subplots(1, 1, figsize=(10, 10))
            ax.set_aspect('equal')
            ax.scatter(x, y, s=1, c='blue', alpha=0.7, label='Lidar scan')
            ax.plot(0, 0, 'r^', markersize=15, label='Drone', zorder=5)
            room = patches.Rectangle((-10, -10), 20, 20, linewidth=2,
                                     edgecolor='gray', facecolor='none', linestyle='--', label='Room')
            ax.add_patch(room)
            ax.annotate('', xy=(0, 1.2), xytext=(0, 0.3),
                        arrowprops=dict(arrowstyle='->', color='red', lw=2))
            ax.text(0.15, 0.8, 'FWD', color='red', fontsize=9, fontweight='bold')
            ax.set_xlabel('East (m)')
            ax.set_ylabel('North (m)')
            ax.set_title(f'2D Lidar — RPLidar A1M8 ({n} points, in-flight)', fontsize=14)
            ax.legend(loc='upper left')
            ax.grid(True, alpha=0.3)
            ax.set_xlim(-12, 12)
            ax.set_ylim(-12, 12)
            outpath = os.path.join(output_dir, "lidar_scan.pdf")
            fig.savefig(outpath, bbox_inches='tight', dpi=150)
            plt.close(fig)
            print(f"  Saved: {outpath}")
    except Exception as e:
        print(f"  Lidar capture error: {e}")

    # --- Optical flow ---
    try:
        px4_bin = os.path.join(REPO_ROOT, "px4", "build/px4_sitl_default/bin")
        result = subprocess.run(
            [f"{px4_bin}/px4-listener", "vehicle_optical_flow", "-n", "1"],
            capture_output=True, text=True, timeout=5
        )
        quality = 0
        for line in result.stdout.split('\n'):
            if 'quality:' in line:
                quality = int(line.split(':')[1].strip())

        fig, ax = plt.subplots(figsize=(8, 3))
        colors = ['#ff4444' if quality < 50 else '#ffaa00' if quality < 150 else '#44cc44']
        ax.barh(['Quality'], [quality], color=colors, height=0.5)
        ax.set_xlim(0, 255)
        ax.set_xlabel('Quality (0-255)')
        ax.set_title('Optical Flow — MTF-01 (in-flight)', fontsize=14)
        ax.text(min(quality + 5, 240), 0, f'{quality}', va='center', fontsize=14, fontweight='bold')
        outpath = os.path.join(output_dir, "optical_flow.pdf")
        fig.savefig(outpath, bbox_inches='tight', dpi=150)
        plt.close(fig)
        print(f"  Saved: {outpath}")
    except Exception as e:
        print(f"  Flow capture error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    os._exit(0)
