#!/usr/bin/env python3
"""
Scarecrow Drone — Wall-Follow v2

Robust, world-agnostic wall-follow using 2D lidar + optical flow:
  1. Connect + wait for local position estimate
  2. Take off to target altitude
  3. Follow chosen wall at target distance
  4. Stop when front wall is confirmed or max duration reached
  5. Land + disarm

Usage:
  python3 scripts/flight/wall_follow_v2.py --side left --wall-distance 2.0
"""
import os
os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

import argparse
import asyncio
import math
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.controllers.front_wall_detector import FrontWallDetector
from scarecrow.controllers.wall_follow import WallFollowController, VelocityCommand
from scarecrow.drone import Drone
from scarecrow.flight.offboard_safety import (
    AltitudeHoldController,
    HealthMonitor,
    SafetyLimits,
    apply_safety,
)
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar

SYSTEM_ADDRESS = "udp://:14540"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--side", choices=["left", "right"], default="left")
    parser.add_argument("--target-alt", type=float, default=2.5)
    parser.add_argument("--wall-distance", type=float, default=2.0)
    parser.add_argument("--forward-speed", type=float, default=0.35)
    parser.add_argument("--front-stop", type=float, default=2.0)
    parser.add_argument("--min-safe", type=float, default=0.6)
    parser.add_argument("--max-seconds", type=float, default=60.0)
    parser.add_argument("--no-yaw-align", action="store_true")
    parser.add_argument("--control-hz", type=float, default=20.0)
    parser.add_argument("--alt-kp", type=float, default=0.6)
    parser.add_argument("--alt-deadband", type=float, default=0.05)
    parser.add_argument("--max-forward", type=float, default=0.6)
    parser.add_argument("--max-lateral", type=float, default=0.45)
    parser.add_argument("--max-vertical", type=float, default=0.4)
    parser.add_argument("--max-yaw", type=float, default=18.0)
    parser.add_argument("--max-height", type=float, default=0.0)
    parser.add_argument("--max-wall-distance", type=float, default=6.0)
    parser.add_argument("--lost-wall-seconds", type=float, default=1.2)
    parser.add_argument("--lost-wall-descend", type=float, default=0.25)
    parser.add_argument("--lost-wall-min-alt", type=float, default=0.8)
    parser.add_argument("--lock-alt", action="store_true")
    parser.add_argument("--health-grace", type=float, default=2.0)
    return parser.parse_args()


async def run() -> None:
    args = parse_args()

    drone = Drone(system_address=SYSTEM_ADDRESS)
    print("Connecting to drone...")
    if not await drone.connect():
        print("ERROR: could not connect to drone")
        return

    print("Waiting for position estimate...")
    if not await drone.wait_for_health():
        print("ERROR: position estimate timed out")
        return

    await drone.set_ekf_origin()

    # Warm up Gazebo topic list so lidar discovery is fast.
    gz_thread, gz_result = prefetch_gz_env_async()
    gz_thread.join(timeout=10)
    gz_env = gz_result.env or {}
    topics = gz_result.topics

    print("Starting lidar...")
    lidar = GazeboLidar(env=gz_env, num_threads=3)
    lidar._topic = lidar._discover_topic(topic_list=topics)
    lidar.start()
    print(f"  Topic: {lidar.topic}")

    for _ in range(30):
        await asyncio.sleep(0.1)
        scan = lidar.get_scan()
        if scan is not None:
            print(
                f"  Lidar ready: front={scan.front_distance():.1f}m "
                f"left={scan.left_distance():.1f}m right={scan.right_distance():.1f}m"
            )
            break
    else:
        print("ERROR: no lidar data")
        lidar.stop()
        return

    print(f"Taking off to {args.target_alt:.1f}m...")
    await drone.prepare_takeoff(args.target_alt)
    await drone.arm()
    if not await drone.takeoff(args.target_alt):
        print("ERROR: takeoff failed")
        await drone.disarm()
        lidar.stop()
        return

    if not await drone.start_offboard():
        print("ERROR: offboard start failed")
        await drone.disarm()
        lidar.stop()
        return

    health = HealthMonitor(drone.system)
    health.start()
    max_height = args.max_height if args.max_height > 0.0 else args.target_alt + 0.6
    altitude_hold = AltitudeHoldController(
        target_alt_m=args.target_alt,
        kp=args.alt_kp,
        deadband_m=args.alt_deadband,
        max_up_speed=args.max_vertical,
        max_down_speed=args.max_vertical,
    )
    limits = SafetyLimits(
        max_forward_speed=args.max_forward,
        max_lateral_speed=args.max_lateral,
        max_vertical_speed=args.max_vertical,
        max_yaw_speed=args.max_yaw,
        max_height=max_height,
        min_wall_distance=args.min_safe,
        health_grace_s=args.health_grace,
    )

    controller = WallFollowController(
        side=args.side,
        target_distance=args.wall_distance,
        forward_speed=args.forward_speed,
        front_stop_distance=args.front_stop,
        min_safe_distance=args.min_safe,
    )
    front_detector = FrontWallDetector(stop_distance_m=args.front_stop)

    print("\n--- Wall Follow v2 ---")
    print(
        f"  side={args.side} wall_distance={args.wall_distance}m "
        f"forward={args.forward_speed}m/s stop={args.front_stop}m"
    )

    start = time.time()
    step = 0
    stop_reason = None
    control_period = 1.0 / max(args.control_hz, 1.0)
    lost_wall_cycles = 0
    lost_wall_limit = max(1, int(args.lost_wall_seconds / control_period))
    try:
        while time.time() - start < args.max_seconds and not controller.done:
            pos = await drone.get_position()
            agl = -(pos.position.down_m - drone.ground_z)

            scan = lidar.get_scan()
            if scan is None:
                down = 0.0 if args.lock_alt else altitude_hold.update(agl)
                await drone.set_velocity(VelocityCommand(down_m_s=down))
                await asyncio.sleep(control_period)
                continue

            if args.side == "left":
                wall_dist = scan.left_distance()
                wall_err = None if args.no_yaw_align else scan.left_wall_angle_error()
            else:
                wall_dist = scan.right_distance()
                wall_err = None if args.no_yaw_align else scan.right_wall_angle_error()

            front_dist = scan.front_distance()
            front_state = front_detector.update(scan)

            wall_valid = math.isfinite(wall_dist) and wall_dist <= args.max_wall_distance
            if not wall_valid:
                lost_wall_cycles += 1
            else:
                lost_wall_cycles = 0
            if lost_wall_cycles >= lost_wall_limit:
                if agl <= args.lost_wall_min_alt:
                    stop_reason = "min_alt_reached"
                    await drone.set_velocity(VelocityCommand())
                    break
                down = min(args.lost_wall_descend, args.max_vertical)
                cmd = VelocityCommand(down_m_s=down)
                cmd, safety_reason = apply_safety(
                    cmd,
                    agl_m=agl,
                    wall_dist_m=wall_dist,
                    front_dist_m=front_dist,
                    limits=limits,
                )
                if safety_reason:
                    stop_reason = safety_reason
                    await drone.set_velocity(cmd)
                    break
                await drone.set_velocity(cmd)
                if step % 20 == 0:
                    elapsed = time.time() - start
                    print(
                        f"  [{elapsed:5.1f}s] wall=inf descending "
                        f"alt={agl:.2f}m vdown={cmd.down_m_s:+.2f}"
                    )
                step += 1
                await asyncio.sleep(control_period)
                continue

            cmd = controller.update(
                wall_dist,
                front_dist,
                wall_angle_error=wall_err,
                front_wall_confirmed=front_state.front_wall_visible,
                front_stop_reached=front_state.stop_confirmed,
            )
            down = 0.0 if args.lock_alt else altitude_hold.update(agl)
            cmd = VelocityCommand(
                forward_m_s=cmd.forward_m_s,
                right_m_s=cmd.right_m_s,
                down_m_s=down,
                yawspeed_deg_s=cmd.yawspeed_deg_s,
            )

            cmd, safety_reason = apply_safety(
                cmd,
                agl_m=agl,
                wall_dist_m=wall_dist,
                front_dist_m=front_dist,
                limits=limits,
            )
            if safety_reason:
                stop_reason = safety_reason
                await drone.set_velocity(cmd)
                break

            since_ok = health.time_since_ok()
            if (not health.is_local_position_ok
                    and since_ok is not None
                    and since_ok > limits.health_grace_s):
                stop_reason = "health_lost"
                await drone.set_velocity(VelocityCommand())
                break

            await drone.set_velocity(cmd)

            if step % 20 == 0:
                elapsed = time.time() - start
                print(
                    f"  [{elapsed:5.1f}s] wall={wall_dist:.2f}m front={front_dist:.2f}m "
                    f"fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f}"
                )

            step += 1
            await asyncio.sleep(control_period)
    finally:
        await health.stop()
        await drone.stop_offboard()
        await drone.land()
        await asyncio.sleep(1)
        await drone.disarm()
        lidar.stop()

    if stop_reason:
        print(f"\nWall follow stopped: {stop_reason}")
    else:
        print("\nWall follow complete.")


if __name__ == "__main__":
    asyncio.run(run())
