#!/usr/bin/env python3
"""
Scarecrow Drone — Hover Test (MAVSDK)

GPS-denied indoor flight using ONLY:
  - Optical flow (MTF-01) for horizontal velocity
  - Downward rangefinder (TF-Luna) for height
  - 2D lidar (RPLidar A1M8) for obstacle avoidance
  - Mono camera (Pi Camera 3) for visual awareness

Sequence: arm -> takeoff to 1m -> hover 5s -> land
Logs altitude and sensor status throughout.

This script runs identically on simulation and real hardware.
Only the connection string changes:
  Sim:  udp://:14540
  Real: serial:///dev/ttyACM0:921600
"""

import asyncio
import subprocess
import os
from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

# --- Configuration ---
SYSTEM_ADDRESS = "udp://:14540"
TARGET_ALT = 1.5  # meters above ground — set higher to ensure 1m+ reached


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

    # --- Verify sensor configuration ---
    print("\n" + "=" * 55)
    print("  SENSOR VERIFICATION — GPS-Denied Navigation")
    print("=" * 55)
    params_check = {
        'EKF2_GPS_CTRL':  (0, "GPS disabled"),
        'EKF2_BARO_CTRL': (0, "Barometer disabled for height"),
        'EKF2_HGT_REF':   (2, "Height reference = rangefinder"),
        'EKF2_OF_CTRL':   (1, "Optical flow enabled"),
        'EKF2_RNG_CTRL':  (1, "Rangefinder enabled"),
    }
    all_ok = True
    for name, (expected, desc) in params_check.items():
        val = int(await drone.param.get_param_int(name))
        ok = val == expected
        print(f"  [{'OK' if ok else 'FAIL'}] {name} = {val} — {desc}")
        if not ok:
            all_ok = False

    if not all_ok:
        print("\nSensor config mismatch! Aborting.")
        return

    print("\n  All params OK: optical flow + rangefinder navigation")
    print("=" * 55)

    # --- Verify all 4 sensor topics are publishing in Gazebo ---
    print("\n--- Gazebo Sensor Topics ---")
    await verify_gz_sensors()

    # --- Log initial position ---
    print("\n--- Flight Sequence ---")
    await log_position(drone, "GROUND")

    # --- Offboard mode ---
    print("Setting initial setpoint...")
    await drone.offboard.set_position_ned(PositionNedYaw(0.0, 0.0, 0.0, 0.0))

    print("Starting offboard mode...")
    try:
        await drone.offboard.start()
    except OffboardError as e:
        print(f"Offboard failed: {e}")
        return
    print("Offboard active")

    # --- Arm ---
    print("Arming...")
    await drone.action.arm()
    print("Armed!")

    # --- Takeoff ---
    print(f"\nTaking off to {TARGET_ALT}m...")
    await drone.offboard.set_position_ned(
        PositionNedYaw(0.0, 0.0, -TARGET_ALT, 0.0)
    )

    for i in range(16):
        await asyncio.sleep(0.5)
        await log_position(drone, f"TAKEOFF {i*0.5:.1f}s")

    # --- Hover ---
    print(f"\nHovering...")
    for i in range(10):
        await asyncio.sleep(0.5)
        await log_position(drone, f"HOVER  {i*0.5:.1f}s")

    # --- Land ---
    print("\nLanding...")
    await drone.action.land()

    for i in range(16):
        await asyncio.sleep(0.5)
        await log_position(drone, f"LAND   {i*0.5:.1f}s")

    # Wait for disarm
    print("\nWaiting for disarm...")
    async for armed in drone.telemetry.armed():
        if not armed:
            break

    try:
        await drone.offboard.stop()
    except Exception:
        pass

    print("\n" + "=" * 55)
    print("  FLIGHT COMPLETE")
    print("  Navigation: optical flow + rangefinder (NO GPS)")
    print("=" * 55)


async def log_position(drone, phase):
    """Log height and velocity."""
    async for pos in drone.telemetry.position_velocity_ned():
        h = -pos.position.down_m
        vz = pos.velocity.down_m_s
        n = pos.position.north_m
        e = pos.position.east_m
        print(f"  [{phase:12s}] alt={h:6.3f}m  vz={vz:+.3f}  n={n:+.3f} e={e:+.3f}")
        break


async def verify_gz_sensors():
    """Check that all 4 sensor topics exist in Gazebo."""
    env = os.environ.copy()
    env["GZ_IP"] = "192.168.68.117"
    env["GZ_PARTITION"] = "px4"

    try:
        result = subprocess.run(
            ["gz", "topic", "-l"],
            capture_output=True, text=True, timeout=5, env=env
        )
        topics = result.stdout
    except Exception as e:
        print(f"  Could not query Gazebo topics: {e}")
        return

    sensors = {
        "Optical flow (MTF-01)":  "optical_flow/optical_flow",
        "Flow camera":            "flow_camera/image",
        "Downward rangefinder":   "lidar_sensor_link/sensor/lidar/scan",
        "2D lidar (RPLidar)":     "lidar_2d_v2",
        "Mono camera (Pi Cam)":   "camera_link/sensor/camera",
    }

    for name, pattern in sensors.items():
        found = pattern in topics
        print(f"  [{'OK' if found else 'MISSING'}] {name}")


if __name__ == "__main__":
    asyncio.run(run())
