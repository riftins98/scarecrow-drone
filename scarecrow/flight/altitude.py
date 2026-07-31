"""Altitude-above-ground helpers and the vertical hold law.

Every mission that flies indoors under a ceiling needs the same three things:
turn a PX4 local position into AGL, decide a vertical speed that holds a target
AGL, and pick a target AGL from an upward rangefinder. They were private
functions in the hangar mission; nothing about them is hangar-specific.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scarecrow.util.math_utils import clamp

# Ceiling clearance the auto takeoff altitude leaves above the drone.
DEFAULT_CEILING_CLEARANCE_M = 2.0

# Vertical hold gains. Deliberately gentle: this runs alongside wall-follow and
# pursuit, and an aggressive vertical term visibly destabilises optical flow,
# which needs a steady view of the floor to track features.
DEFAULT_HOLD_TOLERANCE_M = 0.12
DEFAULT_HOLD_KP = 0.45
DEFAULT_HOLD_MAX_DOWN_SPEED_M_S = 0.18

# How far off target the altitude must drift before a mission logs a warning.
DEFAULT_WARNING_ERROR_M = 0.20


@dataclass(frozen=True)
class AltitudeHoldConfig:
    """Tuning for :func:`altitude_hold_down_speed`."""

    tolerance_m: float = DEFAULT_HOLD_TOLERANCE_M
    kp: float = DEFAULT_HOLD_KP
    max_down_speed_m_s: float = DEFAULT_HOLD_MAX_DOWN_SPEED_M_S
    warning_error_m: float = DEFAULT_WARNING_ERROR_M


def agl_from_position(position, ground_z: float) -> float:
    """Height above ground from a PX4 position report.

    PX4's local frame is NED, so `down_m` grows downward; AGL is its negation
    relative to the ground reference captured at takeoff.
    """
    return -(position.position.down_m - ground_z)


def altitude_hold_down_speed(
    agl_m: float,
    target_alt_m: float,
    *,
    tolerance_m: float = DEFAULT_HOLD_TOLERANCE_M,
    kp: float = DEFAULT_HOLD_KP,
    max_down_speed_m_s: float = DEFAULT_HOLD_MAX_DOWN_SPEED_M_S,
) -> tuple[float, float, bool]:
    """Return ``(down_speed_m_s, error_m, within_tolerance)``.

    MAVSDK body velocity treats positive down as descent, and a positive
    altitude error means "too high", so the proportional term needs no sign
    flip -- error and command share a sign. This is easy to get backwards and
    the failure mode is the drone climbing into the ceiling.

    A non-finite AGL (no position fix yet) commands zero rather than guessing.
    """
    if not math.isfinite(agl_m):
        return 0.0, math.inf, False
    error = agl_m - target_alt_m
    if abs(error) <= tolerance_m:
        return 0.0, error, True
    return clamp(error * kp, -max_down_speed_m_s, max_down_speed_m_s), error, False


def target_alt_from_ceiling_distance(
    ceiling_distance_m: float,
    *,
    target_clearance_m: float = DEFAULT_CEILING_CLEARANCE_M,
) -> float:
    """AGL target that leaves ``target_clearance_m`` below the ceiling.

    Raises rather than clamping when the ceiling is too low: silently choosing
    a lower altitude would fly the mission in a space the operator did not
    approve, and the caller is better placed to abort.
    """
    if not math.isfinite(ceiling_distance_m):
        raise ValueError("ceiling distance must be finite")
    if ceiling_distance_m <= target_clearance_m:
        raise ValueError(
            f"ceiling distance {ceiling_distance_m:.2f}m is not above "
            f"target clearance {target_clearance_m:.2f}m"
        )
    return ceiling_distance_m - target_clearance_m
