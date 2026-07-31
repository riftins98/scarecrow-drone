"""Deriving an arena boundary from flight evidence.

Two independent estimates, combined:

1. A box inferred from the stabilised start pose plus its four lidar readings.
   Available immediately, but only as good as one scan from one place.
2. Wall hits projected from route samples taken during steady wall-following.
   Slower to accumulate, but many samples along each wall.

The second refines the first. Neither alone produced a boundary that matched
the room well enough for a customer-facing map.
"""
from __future__ import annotations

import math
import statistics

from scarecrow.navigation.map_unit import MapUnit
from scarecrow.sensors.lidar.validation import (
    DEFAULT_MAX_DISTANCE_M,
    DEFAULT_MIN_DISTANCE_M,
    valid_distance,
)

# How far a sample's wall distance may sit from the commanded wall distance and
# still count as "the drone was tracking the wall properly here".
DEFAULT_BOUNDARY_SAMPLE_TOLERANCE_M = 0.6

# Fewer hits than this on one side is noise, not evidence.
DEFAULT_BOUNDARY_MIN_SIDE_SAMPLES = 2

# Phases during which the drone holds a steady, wall-referenced pose. Samples
# from turns, pursuit or the entry planner are excluded: the drone is rotating
# or chasing a bird, so its lidar returns say little about where walls are.
STABLE_MAPPING_PHASES = frozenset(
    {"wall_follow", "reverse_leg", "stabilize_landing", "landing"}
)


def arena_boundary_from_start(
    *,
    x: float,
    y: float,
    yaw_deg: float,
    rear_distance: float,
    left_distance: float,
    front_distance: float,
    right_distance: float,
) -> list[dict]:
    """Axis-aligned box from one stabilised pose and its four wall distances."""
    yaw_rad = math.radians(yaw_deg)
    fwd_x = math.cos(yaw_rad)
    fwd_y = math.sin(yaw_rad)
    right_x = -math.sin(yaw_rad)
    right_y = math.cos(yaw_rad)
    wall_points = [
        {"x": x + fwd_x * front_distance, "y": y + fwd_y * front_distance},
        {"x": x - fwd_x * rear_distance, "y": y - fwd_y * rear_distance},
        {"x": x - right_x * left_distance, "y": y - right_y * left_distance},
        {"x": x + right_x * right_distance, "y": y + right_y * right_distance},
    ]
    return MapUnit._axis_aligned_boundary(wall_points)


def project_route_sample_wall_hit(sample: dict, side: str) -> dict | None:
    """Project one route sample's side reading into a world-frame wall hit.

    Returns None for anything unusable rather than raising -- route samples are
    collected best-effort during flight and partial ones are normal.

    ``axis`` records whether the ray pointed mostly along x or y, which is what
    lets the refiner assign the hit to the correct side of an axis-aligned box.
    """
    dist = sample.get(f"{side}_dist")
    if not isinstance(dist, (int, float)) or not math.isfinite(dist):
        return None
    if not valid_distance(dist, min_m=DEFAULT_MIN_DISTANCE_M, max_m=DEFAULT_MAX_DISTANCE_M):
        return None

    yaw_deg = sample.get("yaw_deg")
    x = sample.get("x")
    y = sample.get("y")
    if not all(isinstance(value, (int, float)) for value in (yaw_deg, x, y)):
        return None

    yaw_rad = math.radians(yaw_deg)
    fwd_x = math.cos(yaw_rad)
    fwd_y = math.sin(yaw_rad)
    right_x = -math.sin(yaw_rad)
    right_y = math.cos(yaw_rad)
    vectors = {
        "front": (fwd_x, fwd_y),
        "rear": (-fwd_x, -fwd_y),
        "left": (-right_x, -right_y),
        "right": (right_x, right_y),
    }
    vec_x, vec_y = vectors[side]
    return {
        "x": x + vec_x * dist,
        "y": y + vec_y * dist,
        "axis": "x" if abs(vec_x) >= abs(vec_y) else "y",
    }


def refine_boundary_from_route_samples(
    boundaries: list[dict],
    route_samples: list[dict],
    *,
    wall_distance: float,
    sample_tolerance_m: float = DEFAULT_BOUNDARY_SAMPLE_TOLERANCE_M,
    min_side_samples: int = DEFAULT_BOUNDARY_MIN_SIDE_SAMPLES,
) -> list[dict]:
    """Pull each side of the startup box onto median wall evidence.

    Uses the median, not the mean: a single sample taken while passing a
    doorway or a parked aircraft projects a hit metres past the real wall, and
    one such outlier would drag a mean well outside the room.

    Returns the input unchanged if the result would be degenerate (inverted or
    zero-area), so a bad refinement can never be worse than no refinement.
    """
    if len(boundaries) < 4:
        return boundaries

    xs = [point["x"] for point in boundaries]
    ys = [point["y"] for point in boundaries]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0

    candidates: dict[str, list[float]] = {
        "min_x": [],
        "max_x": [],
        "min_y": [],
        "max_y": [],
    }
    # Scale the tolerance with the wall distance: a mission following a wall at
    # 4m wanders more in absolute terms than one at 1m.
    tolerance = max(sample_tolerance_m, wall_distance * 0.2)

    for sample in route_samples:
        if sample.get("phase") not in STABLE_MAPPING_PHASES:
            continue
        for side in ("front", "rear", "left", "right"):
            dist = sample.get(f"{side}_dist")
            if not isinstance(dist, (int, float)) or not math.isfinite(dist):
                continue
            if abs(dist - wall_distance) > tolerance:
                continue
            hit = project_route_sample_wall_hit(sample, side)
            if hit is None:
                continue
            if hit["axis"] == "x":
                key = "max_x" if hit["x"] >= center_x else "min_x"
                candidates[key].append(hit["x"])
            else:
                key = "max_y" if hit["y"] >= center_y else "min_y"
                candidates[key].append(hit["y"])

    refined = {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y}
    for key, values in candidates.items():
        if len(values) >= min_side_samples:
            refined[key] = statistics.median(values)

    if refined["min_x"] >= refined["max_x"] or refined["min_y"] >= refined["max_y"]:
        return boundaries

    return [
        {"x": refined["min_x"], "y": refined["max_y"]},
        {"x": refined["min_x"], "y": refined["min_y"]},
        {"x": refined["max_x"], "y": refined["min_y"]},
        {"x": refined["max_x"], "y": refined["max_y"]},
    ]
