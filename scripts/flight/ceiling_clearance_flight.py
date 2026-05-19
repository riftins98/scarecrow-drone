#!/usr/bin/env python3
"""Ceiling clearance flight test for the upward TF-Luna-style rangefinder.

Flow:
  1. Take off to 2.5m AGL
  2. Stabilize with the 2D lidar
  3. Climb slowly until upward rangefinder reports target ceiling clearance
  4. Hover
  5. Descend until upward rangefinder reports return ceiling clearance
  6. Hover
  7. Land with lidar hold

Run with Gazebo already launched, usually:
    ./scripts/shell/launch.sh hangar_1
    .venv/bin/python scripts/flight/ceiling_clearance_flight.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time

os.environ["GRPC_VERBOSITY"] = "ERROR"
os.environ["GRPC_ENABLE_FORK_SUPPORT"] = "0"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from mavsdk.offboard import VelocityBodyYawspeed

from scarecrow.controllers.distance_stabilizer import (
    DistanceStabilizerController,
    DistanceTargets,
)
from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.drone import Drone
from scarecrow.flight.helpers import wait_for_stable
from scarecrow.flight.stabilization import lidar_stabilize
from scarecrow.logging_setup import get_logger, log_event, log_run_file_path
from scarecrow.navigation.navigation_unit import NavigationUnit
from scarecrow.sensors import GazeboRangefinder
from scarecrow.sensors.gz_utils import prefetch_gz_env_async
from scarecrow.sensors.lidar.gazebo import GazeboLidar


SYSTEM_ADDRESS = "udp://:14540"
DEFAULT_TARGET_ALT = 2.5
DEFAULT_CEILING_CLEARANCE = 1.5
DEFAULT_RETURN_CEILING_CLEARANCE = 2.5
DEFAULT_HOVER_SECONDS = 3.0

# Hangar spawn stabilization targets. These match the current demo flight
# pattern: hold horizontal position with rear/right wall distances.
LIDAR_TARGET_REAR = 17.0
LIDAR_TARGET_RIGHT = 3.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Flight test for upward ceiling rangefinder clearance."
    )
    parser.add_argument(
        "--target-alt",
        type=float,
        default=DEFAULT_TARGET_ALT,
        help="Initial takeoff altitude in meters AGL.",
    )
    parser.add_argument(
        "--ceiling-clearance",
        type=float,
        default=DEFAULT_CEILING_CLEARANCE,
        help="Stop climbing when upward rangefinder is at or below this value.",
    )
    parser.add_argument("--hover-seconds", type=float, default=DEFAULT_HOVER_SECONDS)
    parser.add_argument(
        "--return-ceiling-clearance",
        type=float,
        default=DEFAULT_RETURN_CEILING_CLEARANCE,
        help="After the near-ceiling hover, descend until TF-Luna reads this ceiling clearance.",
    )
    parser.add_argument("--climb-speed", type=float, default=0.30, help="m/s upward")
    parser.add_argument("--descend-speed", type=float, default=0.20, help="m/s downward")
    parser.add_argument("--max-climb-seconds", type=float, default=60.0)
    parser.add_argument("--max-descend-seconds", type=float, default=30.0)
    parser.add_argument("--system-address", default=SYSTEM_ADDRESS)
    return parser.parse_args()


def _agl(pos, ground_z: float) -> float:
    return -(pos.position.down_m - ground_z)


async def _wait_for_ceiling_sensor(
    ceiling_sensor: GazeboRangefinder,
    timeout: float = 10.0,
) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ceiling_sensor.get_distance_m() is not None:
            return True
        await asyncio.sleep(0.1)
    return False


async def _send_lidar_hold_velocity(
    drone: Drone,
    lidar: GazeboLidar,
    stabilizer: DistanceStabilizerController,
    down_m_s: float,
) -> VelocityCommand:
    scan = lidar.get_scan()
    if scan is None:
        cmd = VelocityCommand(down_m_s=down_m_s)
    else:
        hold_cmd = stabilizer.update(scan)
        cmd = VelocityCommand(
            forward_m_s=hold_cmd.forward_m_s,
            right_m_s=hold_cmd.right_m_s,
            down_m_s=down_m_s,
        )
        if stabilizer.done:
            stabilizer.reset()
    await drone.set_velocity(cmd)
    return cmd


async def _log_ceiling_status(
    drone: Drone,
    ceiling_sensor: GazeboRangefinder,
    label: str,
    started_at: float,
    log,
    cmd: VelocityCommand | None = None,
) -> None:
    pos = await drone.get_position()
    clearance = ceiling_sensor.get_distance_m()
    agl = _agl(pos, drone.ground_z)
    vz_up = -pos.velocity.down_m_s
    cmd_part = ""
    if cmd is not None:
        cmd_part = (
            f"  cmd: fwd={cmd.forward_m_s:+.2f} "
            f"lat={cmd.right_m_s:+.2f} down={cmd.down_m_s:+.2f}"
        )

    if clearance is None:
        print(f"  [{label}] {time.time() - started_at:5.1f}s  agl={agl:.2f}m  ceiling=NO_DATA  vz_up={vz_up:+.2f}{cmd_part}")
        log_event(log, "ceiling_sample", phase=label, agl=round(agl, 3),
                  ceiling_m=None, vz_up=round(vz_up, 3))
        return

    print(
        f"  [{label}] {time.time() - started_at:5.1f}s  "
        f"agl={agl:.2f}m  ceiling={clearance:.2f}m  vz_up={vz_up:+.2f}{cmd_part}"
    )
    log_event(
        log,
        "ceiling_sample",
        phase=label,
        agl=round(agl, 3),
        ceiling_m=round(clearance, 3),
        vz_up=round(vz_up, 3),
    )


async def _hover_with_ceiling_log(
    drone: Drone,
    lidar: GazeboLidar,
    ceiling_sensor: GazeboRangefinder,
    targets: DistanceTargets,
    seconds: float,
    label: str,
    log,
) -> None:
    stabilizer = DistanceStabilizerController(targets=targets)
    started_at = time.time()
    step = 0
    while time.time() - started_at < seconds:
        cmd = await _send_lidar_hold_velocity(drone, lidar, stabilizer, down_m_s=0.0)
        await asyncio.sleep(0.05)
        step += 1
        if step % 5 == 0:
            await _log_ceiling_status(drone, ceiling_sensor, label, started_at, log, cmd)
    await drone.set_velocity(VelocityCommand())


async def _climb_until_ceiling_clearance(
    drone: Drone,
    lidar: GazeboLidar,
    ceiling_sensor: GazeboRangefinder,
    targets: DistanceTargets,
    target_clearance: float,
    climb_speed: float,
    timeout: float,
    log,
) -> bool:
    print(f"\n--- Phase 2: climb until ceiling clearance is {target_clearance:.2f}m ---")
    log_event(log, "phase", phase="climb_to_ceiling_clearance",
              target_clearance=target_clearance, climb_speed=climb_speed)
    stabilizer = DistanceStabilizerController(targets=targets)
    started_at = time.time()
    step = 0

    while time.time() - started_at < timeout:
        clearance = ceiling_sensor.get_distance_m()
        if clearance is not None and clearance <= target_clearance:
            print(f"  Target ceiling clearance reached: {clearance:.2f}m")
            log_event(log, "ceiling_target_reached",
                      clearance=round(clearance, 3),
                      elapsed_s=round(time.time() - started_at, 1))
            await drone.set_velocity(VelocityCommand())
            await wait_for_stable(drone.system, drone.ground_z, stable_secs=1.0)
            return True

        cmd = await _send_lidar_hold_velocity(
            drone,
            lidar,
            stabilizer,
            down_m_s=-abs(climb_speed),
        )
        await asyncio.sleep(0.05)
        step += 1
        if step % 5 == 0:
            await _log_ceiling_status(drone, ceiling_sensor, "climb", started_at, log, cmd)

    print("  ERROR: ceiling clearance target was not reached before timeout")
    log_event(log, "ceiling_target_timeout", timeout=timeout)
    await drone.set_velocity(VelocityCommand())
    return False


async def _descend_to_ceiling_clearance(
    drone: Drone,
    lidar: GazeboLidar,
    ceiling_sensor: GazeboRangefinder,
    targets: DistanceTargets,
    target_clearance: float,
    descend_speed: float,
    log,
    timeout: float = 30.0,
) -> bool:
    print(f"\n--- Phase 4: descend until ceiling clearance is {target_clearance:.2f}m ---")
    log_event(log, "phase", phase="descend_to_ceiling_clearance",
              target_clearance=target_clearance, descend_speed=descend_speed)
    stabilizer = DistanceStabilizerController(targets=targets)
    started_at = time.time()
    step = 0

    while time.time() - started_at < timeout:
        clearance = ceiling_sensor.get_distance_m()
        if clearance is None:
            print("  ERROR: no upward rangefinder data during descent")
            log_event(log, "ceiling_data_lost", phase="descend")
            await drone.set_velocity(VelocityCommand())
            return False

        if clearance >= target_clearance:
            print(f"  Return ceiling clearance reached: {clearance:.2f}m")
            log_event(log, "return_ceiling_clearance_reached",
                      clearance=round(clearance, 3),
                      elapsed_s=round(time.time() - started_at, 1))
            await drone.set_velocity(VelocityCommand())
            await wait_for_stable(drone.system, drone.ground_z, stable_secs=1.0)
            return True

        cmd = await _send_lidar_hold_velocity(
            drone,
            lidar,
            stabilizer,
            down_m_s=abs(descend_speed),
        )
        await asyncio.sleep(0.05)
        step += 1
        if step % 5 == 0:
            await _log_ceiling_status(drone, ceiling_sensor, "descend", started_at, log, cmd)

    print("  ERROR: return ceiling clearance target was not reached before timeout")
    log_event(log, "return_ceiling_clearance_timeout", timeout=timeout)
    await drone.set_velocity(VelocityCommand())
    return False


async def _lidar_locked_land(
    drone: Drone,
    lidar: GazeboLidar,
    ceiling_sensor: GazeboRangefinder,
    targets: DistanceTargets,
    descend_speed: float,
    log,
) -> None:
    print("\n--- Phase 6: lidar-locked landing ---")
    log_event(log, "phase", phase="lidar_locked_land", descend_speed=descend_speed)
    stabilizer = DistanceStabilizerController(targets=targets)
    land_start = time.time()
    step = 0
    last_cmd = VelocityCommand()

    while time.time() - land_start < 30.0:
        scan = lidar.get_scan()
        if scan is not None:
            last_cmd = stabilizer.update(scan)
            await drone.system.offboard.set_velocity_body(
                VelocityBodyYawspeed(
                    last_cmd.forward_m_s,
                    last_cmd.right_m_s,
                    abs(descend_speed),
                    0.0,
                )
            )
            if stabilizer.done:
                stabilizer.reset()
        else:
            await drone.system.offboard.set_velocity_body(
                VelocityBodyYawspeed(0.0, 0.0, abs(descend_speed), 0.0)
            )

        await asyncio.sleep(0.05)
        step += 1
        if step % 5 == 0:
            await _log_ceiling_status(drone, ceiling_sensor, "land", land_start, log, last_cmd)

        pos = await drone.get_position()
        agl = _agl(pos, drone.ground_z)
        if agl < 0.35:
            print(f"  Near ground ({agl:.2f}m), switching to PX4 land")
            break

    await drone.stop_offboard()
    print("Commanding land...")
    await drone.land()

    for _ in range(20):
        await asyncio.sleep(0.2)
        try:
            pos = await asyncio.wait_for(drone.get_position(), timeout=1.0)
            if _agl(pos, drone.ground_z) < 0.15:
                break
        except Exception:
            break

    print("Disarming...")
    if await drone.disarm():
        print("  Disarmed.")
    else:
        print("  WARNING: drone did not disarm cleanly")


async def run() -> None:
    args = parse_args()
    run_id = f"ceiling_clearance_{int(time.time())}"
    log = get_logger("flight.ceiling_clearance", run_id=run_id, prefix="flight")
    log_event(
        log,
        "flight_start",
        run_id=run_id,
        target_alt=args.target_alt,
        ceiling_clearance=args.ceiling_clearance,
        return_ceiling_clearance=args.return_ceiling_clearance,
        hover_seconds=args.hover_seconds,
        log_file=str(log_run_file_path()),
    )

    print("\n" + "=" * 58)
    print("  SCARECROW DRONE — CEILING CLEARANCE FLIGHT TEST")
    print("=" * 58)
    print(f"Run ID:             {run_id}")
    print(f"Takeoff altitude:         {args.target_alt:.2f}m AGL")
    print(f"Near-ceiling clearance:   {args.ceiling_clearance:.2f}m")
    print(f"Return ceiling clearance: {args.return_ceiling_clearance:.2f}m")
    print(f"Hover duration:           {args.hover_seconds:.1f}s")
    print(f"Log file:                 {log_run_file_path()}")

    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)

    gz_thread, gz_result = prefetch_gz_env_async()

    drone = Drone(system_address=args.system_address)
    lidar: GazeboLidar | None = None
    ceiling_sensor: GazeboRangefinder | None = None

    try:
        print("\nConnecting to drone...")
        if not await drone.connect():
            print("ERROR: could not connect to drone")
            return
        print("Connected.")

        await drone.set_ekf_origin()

        print("Waiting for position estimate...")
        if not await drone.wait_for_health():
            print("ERROR: position estimate timed out")
            return
        print("Position OK.")

        print("\n--- Sensor verification ---")
        if not await drone.verify_gps_denied_params(verbose=True):
            print("Sensor config mismatch -- aborting")
            return

        gz_thread.join(timeout=10)
        gz_env = gz_result.env or {}
        topics = gz_result.topics

        print("\nStarting 2D lidar...")
        lidar = GazeboLidar(env=gz_env, num_threads=3)
        lidar._topic = lidar._discover_topic(topic_list=topics)
        lidar.start()
        print(f"  Lidar topic: {lidar.topic}")

        print("Starting upward ceiling rangefinder...")
        ceiling_sensor = GazeboRangefinder(env=gz_env)
        ceiling_sensor._topic = ceiling_sensor._discover_topic(topic_list=topics)
        ceiling_sensor.start()
        print(f"  Ceiling topic: {ceiling_sensor.topic}")

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
            print("ERROR: no 2D lidar data -- aborting")
            return

        if not await _wait_for_ceiling_sensor(ceiling_sensor):
            print("ERROR: no upward rangefinder data -- aborting")
            return
        print(f"  Ceiling rangefinder ready: {ceiling_sensor.get_distance_m():.2f}m")

        targets = DistanceTargets(rear=LIDAR_TARGET_REAR, right=LIDAR_TARGET_RIGHT)
        nav = NavigationUnit(drone, lidar)

        print(f"\nSetting takeoff altitude to {args.target_alt:.2f}m...")
        await drone.prepare_takeoff(args.target_alt)

        print("Arming...")
        await drone.arm()
        print("Armed.")

        print(f"Taking off to {args.target_alt:.2f}m...")
        if not await drone.takeoff(altitude=args.target_alt):
            print("ERROR: takeoff failed")
            return

        if not await drone.start_offboard():
            print("ERROR: offboard start failed")
            return

        print("\n--- Phase 1: stabilize at takeoff altitude ---")
        await nav.stabilize(targets, label="takeoff-stable")
        await _log_ceiling_status(drone, ceiling_sensor, "takeoff-stable", time.time(), log)

        if not await _climb_until_ceiling_clearance(
            drone,
            lidar,
            ceiling_sensor,
            targets,
            target_clearance=args.ceiling_clearance,
            climb_speed=args.climb_speed,
            timeout=args.max_climb_seconds,
            log=log,
        ):
            return

        print(f"\n--- Phase 3: hover near ceiling for {args.hover_seconds:.1f}s ---")
        await _hover_with_ceiling_log(
            drone, lidar, ceiling_sensor, targets, args.hover_seconds, "ceiling-hover", log
        )

        if not await _descend_to_ceiling_clearance(
            drone,
            lidar,
            ceiling_sensor,
            targets,
            target_clearance=args.return_ceiling_clearance,
            descend_speed=args.descend_speed,
            timeout=args.max_descend_seconds,
            log=log,
        ):
            return

        print(
            f"\n--- Phase 5: hover at {args.return_ceiling_clearance:.2f}m "
            f"ceiling clearance for {args.hover_seconds:.1f}s ---"
        )
        await _hover_with_ceiling_log(
            drone, lidar, ceiling_sensor, targets, args.hover_seconds, "return-hover", log
        )

        await lidar_stabilize(drone.system, lidar, targets, label="pre-land")
        await _lidar_locked_land(
            drone,
            lidar,
            ceiling_sensor,
            targets,
            descend_speed=max(args.descend_speed, 0.25),
            log=log,
        )

        log_event(log, "flight_complete")
        print("\nCeiling clearance flight complete.")

    finally:
        if drone.is_armed:
            print("\n[SAFETY] Drone still armed on cleanup -- forcing disarm/kill")
            try:
                await asyncio.wait_for(drone.disarm(), timeout=5.0)
            except Exception as exc:
                print(f"[SAFETY] safety disarm failed: {exc}")
        if lidar is not None:
            lidar.stop()
        if ceiling_sensor is not None:
            ceiling_sensor.stop()


def _cleanup_and_exit(exit_code: int = 0) -> None:
    subprocess.run(["pkill", "-f", "mavsdk_server"], capture_output=True)
    os._exit(exit_code)


if __name__ == "__main__":
    try:
        asyncio.run(run())
        _cleanup_and_exit(0)
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        _cleanup_and_exit(130)
    except Exception as exc:
        print(f"\n[FLIGHT FAILED] {type(exc).__name__}: {exc}", file=sys.stderr)
        _cleanup_and_exit(1)
