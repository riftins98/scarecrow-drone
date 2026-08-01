"""Where the drone is flying: simulation or real hardware.

Mission code depends on `SensorSuite`, never on a concrete backend, so the same
flight logic runs in Gazebo and on the Raspberry Pi.

    from scarecrow.platform import sensor_suite_for

    suite = sensor_suite_for("auto", repo_root=REPO_ROOT)
    await HangarCircuitPursuitMission(config, sensors=suite).run()
"""
from __future__ import annotations

import os

from .base import SensorSuite, TargetRemovalOutcome, WorldServices
from .hardware import HardwareSensorSuite
from .simulation import GazeboSensorSuite, find_drone_camera_topic

__all__ = [
    "SensorSuite",
    "WorldServices",
    "TargetRemovalOutcome",
    "GazeboSensorSuite",
    "HardwareSensorSuite",
    "find_drone_camera_topic",
    "detect_platform",
    "sensor_suite_for",
]


def detect_platform() -> str:
    """Guess the platform: "simulation" or "hardware".

    Deliberately conservative -- it returns "hardware" only on positive
    evidence of a Raspberry Pi, because that path drives real motors. Anything
    ambiguous is simulation, and an operator who disagrees passes an explicit
    value.

    SCARECROW_PLATFORM=simulation|hardware overrides the guess entirely.
    """
    override = os.environ.get("SCARECROW_PLATFORM")
    if override in ("simulation", "hardware"):
        return override

    # The device tree model is the most reliable Pi signal available without
    # importing anything: /proc/cpuinfo varies by kernel and OS image.
    try:
        with open("/proc/device-tree/model", "rb") as fh:
            if b"Raspberry Pi" in fh.read():
                return "hardware"
    except OSError:
        pass
    return "simulation"


def sensor_suite_for(platform: str = "auto", *, repo_root: str | None = None) -> SensorSuite:
    """Build the sensor suite for a platform.

    "auto" detects. Anything else must be "simulation" or "hardware"; an
    unknown value raises rather than defaulting, so a typo in a config cannot
    quietly select the wrong backend.
    """
    if platform == "auto":
        platform = detect_platform()

    if platform == "simulation":
        if repo_root is None:
            raise ValueError("repo_root is required for the simulation sensor suite")
        return GazeboSensorSuite(repo_root=repo_root)
    if platform == "hardware":
        return HardwareSensorSuite()
    raise ValueError(
        f"unknown platform {platform!r} (want 'auto', 'simulation' or 'hardware')"
    )
