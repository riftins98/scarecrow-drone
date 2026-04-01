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

from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed
# commander set_heading 0
# Add repo root to path for scarecrow package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scarecrow.sensors.lidar import LidarScan
from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.controllers.wall_follow import WallFollowController, VelocityCommand

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5
WALL_DISTANCE = 2.0
FORWARD_SPEED = 0.4
FRONT_STOP_DISTANCE = 2.0


async def wait_for_altitude(drone, target_alt, ground_z, timeout=20):
    """Wait until drone reaches target altitude."""
    for i in range(int(timeout / 0.5)):
        await asyncio.sleep(0.5)
        async for pos in drone.telemetry.position_velocity_ned():
            agl = -(pos.position.down_m - ground_z)
            print(f"  Climbing... {agl:.1f}m / {target_alt}m")
            if agl >= target_alt - 0.3:
                return True
            break
    return False


async def run():
    drone = System()
    print("Connecting to drone...")
    await drone.connect(system_address=SYSTEM_ADDRESS)

    print("Waiting for connection...")
    async for state in drone.core.connection_state():
        if state.is_connected:
            print("Connected!")
            break

    print("Waiting for position estimate...")
    async for health in drone.telemetry.health():
        if health.is_local_position_ok:
            print("Position estimate OK")
            break

    # --- Set EKF origin ---
    print("\n--- Pre-flight Setup ---")
    try:
        await drone.action.set_gps_global_origin(0.0, 0.0, 0.0)
        print("  EKF origin set (0, 0, 0)")
    except Exception as e:
        print(f"  set_gps_global_origin failed: {e}")
    print("  (heading must be set manually: commander set_heading 0)")

    # --- Start lidar ---
    print("\n--- Starting Lidar ---")
    lidar = GazeboLidar(num_threads=3)
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

    # --- Get ground reference ---
    await asyncio.sleep(1)
    async for pos in drone.telemetry.position_velocity_ned():
        ground_z = pos.position.down_m
        break
    print(f"  Ground reference: z={ground_z:.3f}")

    # --- Takeoff ---
    print(f"\n--- Takeoff to {TARGET_ALT}m ---")
    await drone.action.set_takeoff_altitude(TARGET_ALT)
    await drone.action.arm()
    print("  Armed!")
    await drone.action.takeoff()
    print("  Taking off...")

    if not await wait_for_altitude(drone, TARGET_ALT, ground_z):
        print("  ERROR: Failed to reach altitude")
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

    # Set initial setpoint (required before offboard.start())
    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )

    try:
        await drone.offboard.start()
        print("  Offboard mode active")
    except OffboardError as e:
        print(f"  Offboard start failed: {e}")
        lidar.stop()
        return

    # --- Wall follow control loop ---
    controller = WallFollowController(
        target_distance=WALL_DISTANCE,
        forward_speed=FORWARD_SPEED,
        front_stop_distance=FRONT_STOP_DISTANCE,
    )

    step = 0
    start_time = time.time()
    try:
        while not controller.done:
            scan = lidar.get_scan()
            if scan is None:
                # No lidar data — hover in place
                await drone.offboard.set_velocity_body(
                    VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
                )
                await asyncio.sleep(0.05)
                continue

            left_dist = scan.left_distance()
            front_dist = scan.front_distance()
            cmd = controller.update(left_dist, front_dist)

            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(
                    cmd.forward_m_s,
                    cmd.right_m_s,
                    cmd.down_m_s,
                    cmd.yawspeed_deg_s,
                )
            )

            if step % 10 == 0:
                elapsed = time.time() - start_time
                print(f"  [{elapsed:5.1f}s] fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} | left={left_dist:.1f}m front={front_dist:.1f}m")

            step += 1
            await asyncio.sleep(0.05)  # ~20 Hz control loop

    except Exception as e:
        print(f"  Control error: {e}")

    elapsed = time.time() - start_time
    print(f"\n--- Wall Follow Complete ({elapsed:.1f}s) ---")

    # --- Stop offboard and land ---
    print("Stopping offboard...")
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass

    await asyncio.sleep(1)

    print("Landing...")
    await drone.action.land()

    # Wait for disarm
    print("Waiting for disarm...")
    try:
        disarm_timeout = asyncio.get_event_loop().time() + 20
        async for armed in drone.telemetry.armed():
            if not armed:
                print("  Disarmed!")
                break
            if asyncio.get_event_loop().time() > disarm_timeout:
                print("  Timeout — disarming")
                await drone.action.disarm()
                break
    except Exception:
        pass

    lidar.stop()

    print("\n" + "=" * 50)
    print("  WALL FOLLOW COMPLETE")
    print(f"  Duration: {elapsed:.1f}s")
    print(f"  Config: {WALL_DISTANCE}m from wall, {FORWARD_SPEED} m/s")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run())
