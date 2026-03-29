#!/usr/bin/env python3
"""
Arm the Scarecrow drone via MAVLink after PX4 SITL starts.
Sets EKF origin and heading, then arms in Stabilized mode.
"""

import time
from pymavlink import mavutil

MAVLINK_HOST = "127.0.0.1"
MAVLINK_PORT = 18570

def wait_for_heartbeat(conn, timeout=30):
    print("Waiting for heartbeat...")
    conn.wait_heartbeat(timeout=timeout)
    print(f"Heartbeat received from system {conn.target_system}")

def set_ekf_origin(conn, lat=0.0, lon=0.0, alt=0.0):
    print("Setting EKF origin...")
    conn.mav.set_gps_global_origin_send(
        conn.target_system,
        int(lat * 1e7),
        int(lon * 1e7),
        int(alt * 1000)
    )
    time.sleep(2)

def set_mode(conn, mode_name):
    mode_id = conn.mode_mapping()[mode_name]
    conn.mav.set_mode_send(
        conn.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        mode_id
    )
    time.sleep(1)

def arm(conn):
    print("Arming...")
    conn.mav.command_long_send(
        conn.target_system,
        conn.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0,
        1, 21196,  # 21196 = force arm magic number
        0, 0, 0, 0, 0
    )
    ack = conn.recv_match(type='COMMAND_ACK', blocking=True, timeout=5)
    if ack and ack.result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        print("Armed successfully!")
    else:
        print(f"Arm result: {ack}")

def main():
    conn = mavutil.mavlink_connection(f"udp:{MAVLINK_HOST}:{MAVLINK_PORT}")
    wait_for_heartbeat(conn)
    time.sleep(3)  # let EKF2 converge
    set_ekf_origin(conn)
    set_mode(conn, "STABILIZE")
    arm(conn)

if __name__ == "__main__":
    main()
