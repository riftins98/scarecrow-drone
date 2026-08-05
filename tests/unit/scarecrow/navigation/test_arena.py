"""Arena boundary estimation from start pose and route evidence.

Moved from tests/unit/scripts/flight/ when this logic left the hangar flight
script for scarecrow.navigation.arena -- it is world-agnostic geometry, not
mission-specific.
"""
from scarecrow.navigation.arena import (
    arena_boundary_from_start,
    refine_boundary_from_route_samples,
)


def test_arena_boundary_from_start_surrounds_start_pose():
    boundary = arena_boundary_from_start(
        x=0.0,
        y=0.0,
        yaw_deg=0.0,
        rear_distance=2.0,
        left_distance=2.0,
        front_distance=10.0,
        right_distance=7.0,
    )

    xs = [p["x"] for p in boundary]
    ys = [p["y"] for p in boundary]
    assert min(xs) == -2.0
    assert max(xs) == 10.0
    assert min(ys) == -2.0
    assert max(ys) == 7.0


def test_refine_boundary_from_route_samples_uses_stable_wall_evidence():
    """Wall-follow evidence pulls the startup box onto the real walls.

    Also asserts pursuit samples are excluded: during a pursuit the drone is
    chasing a bird, not tracking a wall, so its lidar returns say nothing about
    where the room ends.
    """
    boundary = [
        {"x": -4.3, "y": 2.9},
        {"x": -4.3, "y": -3.6},
        {"x": 7.7, "y": -3.6},
        {"x": 7.7, "y": 2.9},
    ]
    samples = [
        # Leg 1 front wall evidence: max X should be near 5.7, not 7.7.
        {
            "phase": "wall_follow",
            "x": 3.7,
            "y": -0.6,
            "yaw_deg": 0.0,
            "front_dist": 2.0,
            "rear_dist": 8.9,
            "left_dist": 2.0,
            "right_dist": 5.0,
        },
        {
            "phase": "wall_follow",
            "x": 3.8,
            "y": -0.5,
            "yaw_deg": 0.0,
            "front_dist": 1.9,
            "rear_dist": 9.0,
            "left_dist": 2.0,
            "right_dist": 5.0,
        },
        # Leg 3 left wall evidence: max Y should be near 3.4, not 2.9.
        {
            "phase": "wall_follow",
            "x": 1.0,
            "y": 1.4,
            "yaw_deg": 180.0,
            "front_dist": 5.0,
            "rear_dist": 6.0,
            "left_dist": 2.0,
            "right_dist": 5.0,
        },
        {
            "phase": "landing",
            "x": 3.6,
            "y": 1.5,
            "yaw_deg": 180.0,
            "front_dist": 8.8,
            "rear_dist": 2.0,
            "left_dist": 2.0,
            "right_dist": 5.0,
        },
        # Pursuit samples are intentionally ignored for boundary correction.
        {
            "phase": "pursuit",
            "x": 0.0,
            "y": 2.0,
            "yaw_deg": 140.0,
            "front_dist": 2.0,
            "rear_dist": 2.0,
            "left_dist": 2.0,
            "right_dist": 2.0,
        },
    ]

    refined = refine_boundary_from_route_samples(
        boundary,
        samples,
        wall_distance=2.0,
    )

    xs = [point["x"] for point in refined]
    ys = [point["y"] for point in refined]
    assert abs(max(xs) - 5.75) < 0.2
    assert abs(max(ys) - 3.45) < 0.2
    assert abs(min(xs) + 4.3) < 0.2
    assert abs(min(ys) + 2.55) < 0.2


def test_refine_boundary_keeps_original_when_no_stable_evidence():
    """A refinement with nothing to go on must not damage the estimate."""
    boundary = [
        {"x": -4.0, "y": 3.0},
        {"x": -4.0, "y": -3.0},
        {"x": 6.0, "y": -3.0},
        {"x": 6.0, "y": 3.0},
    ]

    refined = refine_boundary_from_route_samples(boundary, [], wall_distance=2.0)

    assert refined == boundary
