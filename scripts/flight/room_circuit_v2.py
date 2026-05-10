#!/usr/bin/env python3
"""
Scarecrow Drone — Wall-Following Flight

GPS-denied indoor wall following using 2D lidar + optical flow:
  1. Take off to 2.5m
  2. Stabilize at hover (position hold via optical flow)
  3. Follow the left wall at 2m distance, flying forward at 0.3 m/s
  4. Stop when 2m from the front wall
  5. Land

Drone starts near the east wall (-7, +7) facing north (+X in Gazebo ENU).
Left wall = east wall (Y = +10, 3m to the left). Front wall = north wall (X = 10, 17m ahead).

Prerequisites:
  - Launch sim: PX4_GZ_MODEL_POSE="-7,7,0,0,0,0" ./scripts/shell/launch.sh
  - In pxh>: commander set_heading 0

Usage:
  source .venv-mavsdk/bin/activate
  python3 scripts/flight/wall_follow.py
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import sys
import time

# Add repo root to path for scarecrow package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scarecrow.controllers.front_wall_detector import FrontWallDetector
from scarecrow.controllers.rotation import rotate_90
from scarecrow.controllers.wall_follow import WallFollowController, VelocityCommand
from scarecrow.drone import Drone
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar

# --- Configuration ---
SYSTEM_ADDRESS = "udpin://0.0.0.0:14540"
TARGET_ALT = 2.5
WALL_DISTANCE = 2.0
FORWARD_SPEED = 0.6
FRONT_STOP_DISTANCE = 2.0
NUM_LEGS = 4
TURN_DIRECTION = "right"
MAX_CIRCUITS = 0  # 0 = run forever


def faster_forward_speed(base_speed: float, multiplier: float = 1.5, max_speed: float = 0.8) -> float:
    """Return a faster constant forward speed with a safety cap."""
    return min(max_speed, base_speed * multiplier)


async def run():
    drone = Drone(system_address=SYSTEM_ADDRESS)
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

    # --- Set EKF origin ---
    print("\n--- Pre-flight Setup ---")
    await drone.set_ekf_origin()

    # --- Start lidar ---
    print("\n--- Starting Lidar ---")
    gz_thread, gz_result = prefetch_gz_env_async()
    gz_thread.join(timeout=10)
    gz_env = gz_result.env or {}
    topics = gz_result.topics

    lidar = GazeboLidar(env=gz_env, num_threads=3)
    lidar._topic = lidar._discover_topic(topic_list=topics)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    # Wait for first scan
    for i in range(20):
        await asyncio.sleep(0.5)
        scan = lidar.get_scan()
        if scan is not None:
            print(f"  Lidar ready: {scan.num_samples} samples")
            print(f"  Front: {scan.front_distance():.1f}m  Left: {scan.left_distance():.1f}m  Right: {scan.right_distance():.1f}m")
            break
    else:
        print("  ERROR: No lidar data after 10s")
        lidar.stop()
        return

    # --- Takeoff ---
    print(f"\n--- Takeoff to {TARGET_ALT}m ---")
    await drone.prepare_takeoff(TARGET_ALT)
    await drone.arm()
    print("  Armed!")
    if not await drone.takeoff(TARGET_ALT):
        print("  ERROR: Failed to reach altitude")
        await drone.disarm()
        lidar.stop()
        return

    # --- Stabilize hover ---
    print("\n--- Stabilizing ---")
    await asyncio.sleep(3)
    scan = lidar.get_scan()
    if scan:
        print(f"  Front: {scan.front_distance():.1f}m  Left: {scan.left_distance():.1f}m  Right: {scan.right_distance():.1f}m")

    # --- Transition to offboard ---
    print("\n--- Starting Wall Follow ---")
    print(f"  Target: {WALL_DISTANCE}m from left wall, {FORWARD_SPEED} m/s forward")
    print(f"  Stop when: {FRONT_STOP_DISTANCE}m from front wall")

    if not await drone.start_offboard():
        print("  Offboard start failed")
        await drone.disarm()
        lidar.stop()
        return
    print("  Offboard mode active")

    # --- Wall follow control loop ---
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
                        # No lidar data — hover in place
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

                    if step % 10 == 0:
                        elapsed = time.time() - start_time
                        print(
                            f"  [{elapsed:5.1f}s] fwd={cmd.forward_m_s:+.2f} "
                            f"lat={cmd.right_m_s:+.2f} | left={left_dist:.1f}m "
                            f"front={front_state.robust_front_m:.1f}m"
                        )

                    step += 1
                    await asyncio.sleep(0.05)  # ~20 Hz control loop

                await drone.set_velocity(VelocityCommand())
                print("  Turning corner...")
                ok = await rotate_90(drone.system, lidar, direction=TURN_DIRECTION)
                if not ok:
                    raise RuntimeError("rotation_failed")
            circuits_done += 1

    except KeyboardInterrupt:
        print("\nEmergency landing (Ctrl+C)...")
        await drone.emergency_land()
        lidar.stop()
        return
    except Exception as e:
        print(f"  Control error: {e}")

    print("\n--- Wall Follow Complete ---")

    # --- Stop offboard and land ---
    print("Stopping offboard...")
    await drone.stop_offboard()

    await asyncio.sleep(1)

    print("Landing...")
    await drone.land()
    await asyncio.sleep(1)
    await drone.disarm()

    lidar.stop()

    print("\n" + "=" * 50)
    print("  WALL FOLLOW COMPLETE")
    print(f"  Config: {WALL_DISTANCE}m from wall, {forward_speed:.2f} m/s")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run())
