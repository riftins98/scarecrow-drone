#!/usr/bin/env python3
"""
Scarecrow Drone — Mapping Flight

GPS-denied indoor flight: fly the full room perimeter while building
a 2D occupancy map from lidar scans. Saves:
  - output/room_map.pdf  — occupancy grid image with drone trajectory
  - output/room_map.npz  — serialized map for Phase 2 pigeon detection

Route: 4 legs along walls + 4 turns (identical to room_circuit.py).
Mapping runs as a background asyncio task throughout the flight.

Prerequisites:
  # Clean room:
  PX4_GZ_MODEL_POSE="-7,7,0,0,0,0" ./scripts/shell/launch.sh

  # Room with obstacles (test mapping):
  PX4_GZ_MODEL_POSE="-7,7,0,0,0,0" ./scripts/shell/launch.sh indoor_room_obstacles

Usage:
  source .venv-mavsdk/bin/activate
  python3 scripts/flight/mapping_flight.py
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import sys
import time

from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.controllers.distance_stabilizer import (
    DistanceStabilizerController,
    DistanceTargets,
)
from scarecrow.controllers.wall_follow import WallFollowController
from scarecrow.controllers.rotation import rotate_90
from scarecrow.navigation.mapper import Mapper

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5
WALL_DISTANCE = 2.0
WALL_SIDE = "left"
FORWARD_SPEED = 0.45
FRONT_STOP_DISTANCE = 2.0
NUM_LEGS = 4
MIN_SAFE_DISTANCE = 1.8
POST_TURN_SIDE_TARGET = 2.2
POST_TURN_REAR_TARGET = 2.2
POST_TURN_TOLERANCE = 0.15
POST_TURN_STABLE_TIME = 1.0
POST_TURN_TIMEOUT = 12.0
MAP_MARGIN_M = 20.0
MAP_SIZE_M = 40.0
MAPPER_RATE_HZ = 20.0
PAUSE_MAPPING_DURING_TURN = True

TURN_DIRECTION = "left" if WALL_SIDE == "right" else "right"


async def wait_for_altitude(drone, target_alt, ground_z, timeout=20):
    for _ in range(int(timeout / 0.5)):
        await asyncio.sleep(0.5)
        async for pos in drone.telemetry.position_velocity_ned():
            agl = -(pos.position.down_m - ground_z)
            print(f"  Climbing... {agl:.1f}m / {target_alt}m")
            if agl >= target_alt - 0.3:
                return True
            break
    return False


async def do_turn(drone, lidar):
    turn_num = getattr(do_turn, "_count", 0) + 1
    do_turn._count = turn_num
    result = await rotate_90(
        drone,
        lidar,
        direction=TURN_DIRECTION,
        compass_overshoot=90.0,
        compass_speed=18.0,
        compass_tolerance=2.0,
    )
    return result


async def stabilize_after_turn(drone, lidar, leg_num):
    print(
        f"  Stabilizing after turn {leg_num}: "
        f"{WALL_SIDE}={POST_TURN_SIDE_TARGET:.1f}m, rear={POST_TURN_REAR_TARGET:.1f}m"
    )
    targets = DistanceTargets(
        rear=POST_TURN_REAR_TARGET,
        left=POST_TURN_SIDE_TARGET if WALL_SIDE == "left" else None,
        right=POST_TURN_SIDE_TARGET if WALL_SIDE == "right" else None,
    )
    stabilizer = DistanceStabilizerController(
        targets=targets,
        kp_front_rear=0.40,
        kp_left_right=0.45,
        max_forward_speed=0.25,
        max_lateral_speed=0.25,
        tolerance=POST_TURN_TOLERANCE,
        stable_time=POST_TURN_STABLE_TIME,
    )
    started = time.time()
    while time.time() - started < POST_TURN_TIMEOUT:
        scan = lidar.get_scan()
        if scan is None:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            await asyncio.sleep(0.05)
            continue
        cmd = stabilizer.update(scan)
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, 0.0, 0.0)
        )
        if stabilizer.done:
            side_dist = scan.right_distance() if WALL_SIDE == "right" else scan.left_distance()
            rear_dist = scan.rear_distance()
            print(f"  Stabilized: {WALL_SIDE}={side_dist:.2f}m rear={rear_dist:.2f}m")
            break
        await asyncio.sleep(0.05)
    else:
        print("  Stabilization timeout — continuing")
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
    await asyncio.sleep(0.5)


async def fly_leg(drone, lidar, leg_num):
    controller = WallFollowController(
        side=WALL_SIDE,
        target_distance=WALL_DISTANCE,
        forward_speed=FORWARD_SPEED,
        front_stop_distance=FRONT_STOP_DISTANCE,
    )
    step = 0
    start_time = time.time()

    while not controller.done:
        scan = lidar.get_scan()
        if scan is None:
            await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
            await asyncio.sleep(0.05)
            continue

        left_dist = scan.left_distance()
        front_dist = scan.front_distance()
        right_dist = scan.right_distance()

        if WALL_SIDE == "right":
            wall_dist = right_dist
            wall_err = scan.right_wall_angle_error()
        else:
            wall_dist = left_dist
            wall_err = scan.left_wall_angle_error()

        cmd = controller.update(wall_dist, front_dist, wall_err)

        safe_fwd = cmd.forward_m_s
        safe_lat = cmd.right_m_s
        if front_dist < MIN_SAFE_DISTANCE:
            safe_fwd = min(safe_fwd, 0.0)
        if left_dist < MIN_SAFE_DISTANCE:
            safe_lat = max(safe_lat, 0.15)
        if right_dist < MIN_SAFE_DISTANCE:
            safe_lat = min(safe_lat, -0.15)

        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(safe_fwd, safe_lat, cmd.down_m_s, cmd.yawspeed_deg_s)
        )

        if step % 10 == 0:
            elapsed = time.time() - start_time
            print(
                f"  [Leg {leg_num} {elapsed:5.1f}s] "
                f"fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} | "
                f"{WALL_SIDE}={wall_dist:.1f}m front={front_dist:.1f}m"
            )
        step += 1
        await asyncio.sleep(0.05)

    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
    await asyncio.sleep(1)
    elapsed = time.time() - start_time
    print(f"  Leg {leg_num} complete ({elapsed:.1f}s)")


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

    try:
        await drone.telemetry.set_rate_position_velocity_ned(MAPPER_RATE_HZ)
        await drone.telemetry.set_rate_attitude_euler(MAPPER_RATE_HZ)
        print(f"Telemetry rates set to {MAPPER_RATE_HZ:.0f}Hz")
    except Exception as e:
        print(f"Telemetry rate setup failed: {e}")

    print("\n--- Pre-flight Setup ---")
    try:
        await drone.action.set_gps_global_origin(0.0, 0.0, 0.0)
        print("  EKF origin set")
    except Exception as e:
        print(f"  set_gps_global_origin failed: {e}")
    print("  Heading initialized by launcher startup hook")

    print("\n--- Starting Lidar ---")
    lidar = GazeboLidar(num_threads=3)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for _ in range(20):
        await asyncio.sleep(0.5)
        scan = lidar.get_scan()
        if scan is not None:
            print(f"  Lidar ready: {scan.num_samples} samples")
            print(
                f"  Front: {scan.front_distance():.1f}m  "
                f"Left: {scan.left_distance():.1f}m  "
                f"Right: {scan.right_distance():.1f}m"
            )
            break
    else:
        print("  ERROR: No lidar data")
        lidar.stop()
        return

    async for pos in drone.telemetry.position_velocity_ned():
        ground_z = pos.position.down_m
        break

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

    print("\n--- Stabilizing ---")
    await asyncio.sleep(3)

    # --- Anchor map to drone's current NED position ---
    # EKF NED origin is set relative to where the drone armed, not the room center.
    # Read the hover position so the map grid covers the actual flight area.
    async for pos in drone.telemetry.position_velocity_ned():
        hover_north = pos.position.north_m
        hover_east = pos.position.east_m
        break
    # Use a larger map around the hover point to prevent clipping when
    # local NED origin is not aligned to room coordinates.
    map_origin_n = hover_north - MAP_MARGIN_M
    map_origin_e = hover_east - MAP_MARGIN_M
    print(f"\n--- Starting Mapper (origin N={map_origin_n:.1f} E={map_origin_e:.1f}) ---")
    mapper = Mapper(lidar, drone,
                    origin_n=map_origin_n,
                    origin_e=map_origin_e,
                    size_m=MAP_SIZE_M)
    mapper_task = asyncio.create_task(mapper.run())

    print("\n--- Starting Mapping Flight ---")
    print(
        f"  {NUM_LEGS} legs, {WALL_DISTANCE}m from wall, {FORWARD_SPEED} m/s\n"
        f"  Post-turn targets: side={POST_TURN_SIDE_TARGET}m rear={POST_TURN_REAR_TARGET}m"
    )

    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
    try:
        await drone.offboard.start()
        print("  Offboard mode active\n")
    except OffboardError as e:
        print(f"  Offboard start failed: {e}")
        mapper.stop()
        await mapper_task
        lidar.stop()
        return

    circuit_start = time.time()

    try:
        for leg in range(1, NUM_LEGS + 1):
            print(f"=== LEG {leg}/{NUM_LEGS} ===")
            await fly_leg(drone, lidar, leg)

            print(f"\n=== TURN {leg} (90° {TURN_DIRECTION}) ===")
            if PAUSE_MAPPING_DURING_TURN:
                mapper.pause()
                print("  Mapper paused during turn+stabilize")
            await do_turn(drone, lidar)
            await stabilize_after_turn(drone, lidar, leg)
            if PAUSE_MAPPING_DURING_TURN:
                mapper.resume()
                print("  Mapper resumed")
            print()

    except Exception as e:
        print(f"\n  Flight error: {e}")

    # --- Stop mapper ---
    print("\n--- Stopping Mapper ---")
    mapper.stop()
    await mapper_task

    # --- Stop offboard and land ---
    print("\n--- Circuit Complete — Landing ---")
    try:
        await drone.offboard.stop()
    except OffboardError:
        pass

    await asyncio.sleep(1)
    print("Landing...")
    await drone.action.land()

    print("Waiting for disarm...")
    try:
        disarm_timeout = asyncio.get_event_loop().time() + 20
        async for armed in drone.telemetry.armed():
            if not armed:
                print("  Disarmed!")
                break
            if asyncio.get_event_loop().time() > disarm_timeout:
                await drone.action.disarm()
                break
    except Exception:
        pass

    lidar.stop()

    # --- Save map outputs ---
    print("\n--- Saving Map ---")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    map_pdf = os.path.join(OUTPUT_DIR, "room_map.pdf")
    map_npz = os.path.join(OUTPUT_DIR, "room_map.npz")

    mapper.map.save_pdf(map_pdf, trajectory=mapper.trajectory)
    mapper.map.save_npz(map_npz, trajectory=mapper.trajectory)

    print("\n" + "=" * 50)
    print("  MAPPING FLIGHT COMPLETE")
    print(f"  Legs: {NUM_LEGS}")
    print(f"  Total time: {time.time() - circuit_start:.1f}s")
    print(f"  Pose samples: {len(mapper.trajectory)}")
    print(f"  Map PDF:  {map_pdf}")
    print(f"  Map NPZ:  {map_npz}")
    print("=" * 50)
    print("\nVerify output:")
    print(f"  open {map_pdf}")
    print(f"  python3 -c \"import numpy as np; d=np.load('{map_npz}'); print(d['grid'].shape, d['resolution'])\"")

    try:
        drone._stop_mavsdk_server()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(run())
