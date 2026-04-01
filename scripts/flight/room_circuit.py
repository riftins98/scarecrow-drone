#!/usr/bin/env python3
"""
Scarecrow Drone — Full Room Circuit

GPS-denied indoor flight: fly the full perimeter of the room and land
at the exact starting position.

Route (4 legs, 4 turns):
  1. Fly forward along left wall → stop 2m from front wall
  2. Turn 90° right
  3. Repeat for all 4 walls
  4. Land at starting position

Uses: 2D lidar (wall following) + optical flow (position hold) + rangefinder (altitude)

Prerequisites:
  - Launch: PX4_GZ_MODEL_POSE="-7,7,0,0,0,0" ./scripts/shell/launch.sh
  - In pxh>: commander set_heading 0

Usage:
  source .venv-mavsdk/bin/activate
  python3 scripts/flight/room_circuit.py
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import asyncio
import math
import sys
import time

from mavsdk import System
from mavsdk.offboard import OffboardError, VelocityBodyYawspeed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

from scarecrow.sensors.lidar.gazebo import GazeboLidar
from scarecrow.controllers.wall_follow import WallFollowController
from scarecrow.controllers.rotation import rotate_90

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(REPO_ROOT, "output")

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 2.5
WALL_DISTANCE = 2.0
WALL_SIDE = "right"
FORWARD_SPEED = 0.4
FRONT_STOP_DISTANCE = 2.2
NUM_LEGS = 4
MIN_SAFE_DISTANCE = 1.5  # emergency override if any wall closer than this


def save_lidar_scan_pdf(label, scan, filename):
    """Save a single lidar scan to a PDF.

    Args:
        label: Title for the plot.
        scan: LidarScan to render.
        filename: Output filename (e.g., "circuit_leg1.pdf").
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    angles = scan.angles
    ranges = scan.ranges
    valid = (ranges > 0.1) & (ranges < 30.0)

    x = ranges[valid] * np.cos(angles[valid])
    y = ranges[valid] * np.sin(angles[valid])

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.scatter(x, y, s=1, c='blue', alpha=0.7, label='Lidar scan')
    ax.plot(0, 0, 'r^', markersize=12, label='Drone')
    ax.annotate('', xy=(1.0, 0), xytext=(0, 0),
                arrowprops=dict(arrowstyle='->', color='red', lw=2))
    ax.text(0.5, 0.3, 'FWD', color='red', fontsize=9, fontweight='bold')
    ax.set_aspect('equal')
    ax.set_title(f'Room Circuit — {label}', fontsize=14)
    ax.set_xlabel('Forward (m)')
    ax.set_ylabel('Left (m)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-12, 12)
    ax.set_ylim(-12, 12)

    # Annotate distances
    front = scan.front_distance()
    left = scan.left_distance()
    right = scan.right_distance()
    ax.text(0.02, 0.02, f'Front: {front:.1f}m  Left: {left:.1f}m  Right: {right:.1f}m',
            transform=ax.transAxes, fontsize=9, verticalalignment='bottom',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

    outpath = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(outpath, bbox_inches='tight', dpi=150)
    plt.close(fig)
    print(f"  Saved: {outpath}")


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


TURN_DIRECTION = "left" if WALL_SIDE == "right" else "right"


async def do_turn(drone, lidar):
    """Turn 90° with scan diagnostics. Delegates to scarecrow.controllers.rotation."""
    turn_num = getattr(do_turn, '_count', 0) + 1
    do_turn._count = turn_num

    # Save pre-turn scan
    pre_scan = lidar.get_scan()
    if pre_scan:
        wall_err_fn = pre_scan.right_wall_angle_error if WALL_SIDE == "right" else pre_scan.left_wall_angle_error
        err = wall_err_fn()
        err_str = f"{math.degrees(err):.1f}°" if err else "N/A"
        print(f"  Pre-turn wall alignment: {err_str}")
        save_lidar_scan_pdf(f"Turn {turn_num} - before", pre_scan, f"circuit_turn{turn_num}_1_before.pdf")

    result = await rotate_90(drone, lidar, direction=TURN_DIRECTION)

    # Save post-turn scan
    post_scan = lidar.get_scan()
    if post_scan:
        save_lidar_scan_pdf(f"Turn {turn_num} - aligned", post_scan, f"circuit_turn{turn_num}_2_aligned.pdf")

    return result


async def fly_leg(drone, lidar, leg_num):
    """Fly one leg of the circuit: forward along wall until front wall."""
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
            await drone.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
            )
            await asyncio.sleep(0.05)
            continue

        left_dist = scan.left_distance()
        front_dist = scan.front_distance()
        right_dist = scan.right_distance()

        # Get wall distance and angle for the followed side
        if WALL_SIDE == "right":
            wall_dist = right_dist
            wall_err = scan.right_wall_angle_error()
        else:
            wall_dist = left_dist
            wall_err = scan.left_wall_angle_error()

        cmd = controller.update(wall_dist, front_dist, wall_err)

        # --- Safety override: push away from any wall closer than MIN_SAFE_DISTANCE ---
        safe_fwd = cmd.forward_m_s
        safe_lat = cmd.right_m_s

        if front_dist < MIN_SAFE_DISTANCE:
            safe_fwd = min(safe_fwd, 0.0)
        if left_dist < MIN_SAFE_DISTANCE:
            safe_lat = max(safe_lat, 0.15)
        if right_dist < MIN_SAFE_DISTANCE:
            safe_lat = min(safe_lat, -0.15)

        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(
                safe_fwd, safe_lat, cmd.down_m_s, cmd.yawspeed_deg_s
            )
        )

        if step % 10 == 0:
            elapsed = time.time() - start_time
            print(f"  [Leg {leg_num} {elapsed:5.1f}s] fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} | {WALL_SIDE}={wall_dist:.1f}m front={front_dist:.1f}m")

        step += 1
        await asyncio.sleep(0.05)

    # Stop
    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )
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

    # --- Pre-flight ---
    print("\n--- Pre-flight Setup ---")
    try:
        await drone.action.set_gps_global_origin(0.0, 0.0, 0.0)
        print("  EKF origin set")
    except Exception as e:
        print(f"  set_gps_global_origin failed: {e}")
    print("  (heading must be set manually: commander set_heading 0)")

    # --- Start lidar ---
    print("\n--- Starting Lidar ---")
    lidar = GazeboLidar(num_threads=3)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for i in range(20):
        await asyncio.sleep(0.5)
        scan = lidar.get_scan()
        if scan is not None:
            print(f"  Lidar ready: {scan.num_samples} samples")
            print(f"  Front: {scan.front_distance():.1f}m  Left: {scan.left_distance():.1f}m  Right: {scan.right_distance():.1f}m")
            break
    else:
        print("  ERROR: No lidar data")
        lidar.stop()
        return

    # --- Takeoff ---
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

    # --- Stabilize ---
    print("\n--- Stabilizing ---")
    await asyncio.sleep(3)

    # --- Start offboard ---
    print("\n--- Starting Room Circuit ---")
    print(f"  {NUM_LEGS} legs, {WALL_DISTANCE}m from wall, {FORWARD_SPEED} m/s")

    await drone.offboard.set_velocity_body(
        VelocityBodyYawspeed(0.0, 0.0, 0.0, 0.0)
    )
    try:
        await drone.offboard.start()
        print("  Offboard mode active\n")
    except OffboardError as e:
        print(f"  Offboard start failed: {e}")
        lidar.stop()
        return

    # --- Fly the circuit ---
    circuit_start = time.time()
    scan_log = []

    # Capture and save start position
    start_scan = lidar.get_scan()
    if start_scan:
        save_lidar_scan_pdf("Start", start_scan, "circuit_start.pdf")

    try:
        for leg in range(1, NUM_LEGS + 1):
            print(f"=== LEG {leg}/{NUM_LEGS} ===")
            await fly_leg(drone, lidar, leg)

            # Capture and save immediately after each leg
            leg_scan = lidar.get_scan()
            if leg_scan:
                save_lidar_scan_pdf(f"Leg {leg} end", leg_scan, f"circuit_leg_{leg}_end.pdf")

            print(f"\n=== TURN {leg} (90° {TURN_DIRECTION}) ===")
            await do_turn(drone, lidar)

            # Save after turn
            turn_scan = lidar.get_scan()
            if turn_scan:
                save_lidar_scan_pdf(f"After turn {leg}", turn_scan, f"circuit_after_turn_{leg}.pdf")
            print()

    except Exception as e:
        print(f"\n  Flight error: {e}")

    # --- Stop and land ---
    print("\n--- Circuit Complete ---")
    print("Stopping offboard...")
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
                print("  Timeout — disarming")
                await drone.action.disarm()
                break
    except Exception:
        pass

    lidar.stop()

    print("\n" + "=" * 50)
    print("  ROOM CIRCUIT COMPLETE")
    print(f"  Legs: {NUM_LEGS}")
    print(f"  Total time: {time.time() - circuit_start:.1f}s")
    print(f"  Config: {WALL_DISTANCE}m from wall, {FORWARD_SPEED} m/s")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(run())
