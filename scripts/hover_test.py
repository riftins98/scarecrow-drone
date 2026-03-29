#!/usr/bin/env python3
"""
Scarecrow Drone — Hover Test
Takeoff to 1m, hover 5 seconds, land.
Requires PX4 SITL running with MAVLink on port 14540.
"""

import time
from pymavlink import mavutil

MAVLINK_PORT = 14540
TARGET_ALT = 1.0  # meters above ground (NED z = -1.0)


def connect():
    print("Connecting to PX4...")
    conn = mavutil.mavlink_connection(f"udpin:0.0.0.0:{MAVLINK_PORT}")
    msg = conn.wait_heartbeat(timeout=15)
    if msg is None:
        print("ERROR: No heartbeat received.")
        exit(1)
    print(f"Connected to system {conn.target_system}")
    return conn


def set_ekf_origin(conn):
    print("Setting EKF origin...")
    conn.mav.set_gps_global_origin_send(
        conn.target_system,
        int(0 * 1e7), int(0 * 1e7), int(0 * 1000)
    )
    time.sleep(2)


def send_position_setpoint(conn, x=0.0, y=0.0, z=-TARGET_ALT):
    """Send local NED position setpoint. z negative = up."""
    conn.mav.set_position_target_local_ned_send(
        0,
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        0b110111111000,  # only position bits enabled
        x, y, z,
        0, 0, 0,
        0, 0, 0,
        0, 0
    )


def set_offboard_mode(conn):
    """Switch to PX4 offboard mode via MAV_CMD_DO_SET_MODE."""
    print("Switching to Offboard mode...")
    conn.mav.command_long_send(
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        6,   # PX4 main mode 6 = Offboard
        0, 0, 0, 0, 0
    )
    time.sleep(1)


def arm(conn):
    print("Arming...")
    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 21196, 0, 0, 0, 0, 0
    )
    ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
    if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        print("Armed!")
    else:
        print(f"Arm failed: {ack}")
        exit(1)


def land(conn):
    print("Landing...")
    conn.mav.command_long_send(
        conn.target_system, conn.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
        0, 0, 0, 0, 0, 0, 0, 0
    )
    # Keep sending setpoints while landing
    start = time.time()
    while time.time() - start < 6:
        send_position_setpoint(conn, z=0.0)
        time.sleep(0.1)
    print("Landed.")


def main():
    conn = connect()
    set_ekf_origin(conn)

    # Step 1: stream setpoints BEFORE switching to offboard (required by PX4)
    print("Pre-streaming setpoints...")
    for _ in range(30):
        send_position_setpoint(conn)
        time.sleep(0.05)

    # Step 2: switch to offboard
    set_offboard_mode(conn)

    # Step 3: arm
    arm(conn)

    # Step 4: takeoff — keep streaming setpoints at 1m
    print(f"Taking off to {TARGET_ALT}m...")
    start = time.time()
    while time.time() - start < 6:
        send_position_setpoint(conn)
        time.sleep(0.05)
    print("Hovering...")

    # Step 5: hover for 5 seconds
    start = time.time()
    while time.time() - start < 5:
        send_position_setpoint(conn)
        time.sleep(0.05)

    # Step 6: land
    land(conn)


if __name__ == "__main__":
    main()
