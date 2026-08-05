"""Numeric helpers used across controllers and missions."""
from __future__ import annotations


def clamp(value: float, lo: float, hi: float) -> float:
    """Constrain ``value`` to the inclusive range [lo, hi]."""
    return max(lo, min(hi, value))


def normalize_angle(deg: float) -> float:
    """Wrap an angle in degrees to (-180, 180].

    Yaw arithmetic in this project mixes PX4 headings, lidar-derived wall
    angles and planner deltas, so nearly every angular comparison needs this
    first. Without it a turn from +179 to -179 reads as a 358-degree error and
    the drone rotates almost all the way round to reach a heading two degrees
    away.
    """
    while deg > 180:
        deg -= 360
    while deg < -180:
        deg += 360
    return deg
