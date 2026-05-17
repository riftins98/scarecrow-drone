#!/usr/bin/env python3
"""Check the upward TF-Luna-style ceiling rangefinder in Gazebo.

Run after launching a world with the drone, for example:
    ./scripts/shell/launch.sh hangar_1
    .venv/bin/python scripts/flight/check_ceiling_rangefinder.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)

from scarecrow.sensors import GazeboRangefinder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read the upward ceiling rangefinder and report clearance."
    )
    parser.add_argument(
        "--topic",
        help="Explicit Gazebo scan topic. Defaults to auto-discovery.",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=10,
        help="Number of readings to collect.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.25,
        help="Seconds between printed readings.",
    )
    parser.add_argument(
        "--min-clearance",
        type=float,
        default=0.8,
        help="Fail if any valid reading is below this ceiling clearance in meters.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=float,
        default=10.0,
        help="Seconds to wait for the first reading.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sensor = GazeboRangefinder(topic=args.topic)

    try:
        sensor.start()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Start Gazebo first, for example: ./scripts/shell/launch.sh hangar_1")
        return 2

    print(f"Topic: {sensor.topic}")
    deadline = time.time() + args.startup_timeout
    readings: list[float] = []

    try:
        while time.time() < deadline and sensor.get_distance_m() is None:
            time.sleep(0.1)

        if sensor.get_distance_m() is None:
            print("ERROR: No ceiling rangefinder readings received")
            return 3

        for idx in range(args.samples):
            distance = sensor.get_distance_m()
            if distance is None:
                print(f"{idx + 1:02d}: no reading")
            else:
                readings.append(distance)
                state = "LOW" if distance < args.min_clearance else "OK"
                print(f"{idx + 1:02d}: ceiling clearance {distance:.3f} m [{state}]")
            time.sleep(args.interval)
    finally:
        sensor.stop()

    if not readings:
        print("ERROR: No valid ceiling clearance readings")
        return 3

    min_reading = min(readings)
    print(f"Minimum clearance: {min_reading:.3f} m")
    if min_reading < args.min_clearance:
        print(f"ERROR: clearance below threshold {args.min_clearance:.3f} m")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
