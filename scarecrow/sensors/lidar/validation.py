"""Sanity checks and simple reads over a lidar scan.

A `LidarScan` reports `inf` when nothing is within range and can return
implausibly small values when the drone is close to its own gear or a mesh
seam. Mapping and stabilisation both need "is this reading usable?", and every
mission was answering it privately with its own magic numbers.
"""
from __future__ import annotations

import math

from scarecrow.controllers.distance_stabilizer import DistanceTargets

# Plausible indoor range. Below the minimum is almost certainly the drone
# seeing itself; above the maximum is beyond any room this system flies in.
DEFAULT_MIN_DISTANCE_M = 0.2
DEFAULT_MAX_DISTANCE_M = 20.0


def valid_distance(
    value: float,
    *,
    min_m: float = DEFAULT_MIN_DISTANCE_M,
    max_m: float = DEFAULT_MAX_DISTANCE_M,
) -> bool:
    """Whether a single distance reading is finite and plausible."""
    return math.isfinite(value) and min_m <= value <= max_m


def scan_valid_for_map(
    scan,
    *,
    min_m: float = DEFAULT_MIN_DISTANCE_M,
    max_m: float = DEFAULT_MAX_DISTANCE_M,
) -> bool:
    """Whether all four cardinal readings are usable as a map sample.

    Deliberately strict -- all four, not any. A partial sample projects wall
    hits from a pose the scan cannot actually corroborate, and those bad hits
    are what drag a boundary estimate out of shape.
    """
    if scan is None or scan.num_samples == 0:
        return False
    distances = (
        scan.front_distance(),
        scan.rear_distance(),
        scan.left_distance(),
        scan.right_distance(),
    )
    return all(valid_distance(d, min_m=min_m, max_m=max_m) for d in distances)


def nearest_start_side(scan, *, fallback_side: str = "left") -> str:
    """Pick the side wall forming the nearest rear corner from the current yaw.

    Falls back rather than raising when neither side is usable: the caller is
    mid-flight and a defensible default beats an exception.
    """
    left = scan.left_distance()
    right = scan.right_distance()
    left_valid = valid_distance(left)
    right_valid = valid_distance(right)
    if left_valid and right_valid:
        return "left" if left <= right else "right"
    if left_valid:
        return "left"
    if right_valid:
        return "right"
    return fallback_side


def current_landing_targets(lidar, *, fallback_wall_distance: float) -> DistanceTargets:
    """Freeze the current rear/left distances as landing hold targets.

    Landing should hold wherever the drone already is, not fly somewhere first.
    Any unusable reading falls back to the mission's wall distance so the
    stabiliser still has a finite setpoint to work against.
    """
    scan = lidar.get_scan()
    if scan is None:
        return DistanceTargets(rear=fallback_wall_distance, left=fallback_wall_distance)

    rear = scan.rear_distance()
    left = scan.left_distance()
    if not valid_distance(rear):
        rear = fallback_wall_distance
    if not valid_distance(left):
        left = fallback_wall_distance
    return DistanceTargets(rear=rear, left=left)
