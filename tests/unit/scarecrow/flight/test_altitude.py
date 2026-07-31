"""Altitude-above-ground helpers and the vertical hold law.

Moved from tests/unit/scripts/flight/ when this left the hangar flight script
for scarecrow.flight.altitude.
"""
import pytest

from scarecrow.flight.altitude import (
    DEFAULT_HOLD_TOLERANCE_M,
    altitude_hold_down_speed,
    target_alt_from_ceiling_distance,
)


def test_target_alt_from_ceiling_distance_leaves_configured_clearance():
    """Automatic target altitude preserves configured ceiling clearance."""
    assert target_alt_from_ceiling_distance(8.0) == 6.0


def test_target_alt_from_ceiling_distance_rejects_low_ceiling():
    """Rejects rather than clamping: flying lower than asked is the caller's call."""
    with pytest.raises(ValueError):
        target_alt_from_ceiling_distance(1.5)


def test_target_alt_from_ceiling_distance_rejects_non_finite():
    with pytest.raises(ValueError):
        target_alt_from_ceiling_distance(float("inf"))


def test_altitude_hold_commands_descent_when_too_high():
    down, error, ok = altitude_hold_down_speed(2.8, 2.5)

    assert down > 0.0
    assert error > 0.0
    assert ok is False


def test_altitude_hold_commands_climb_when_too_low():
    down, error, ok = altitude_hold_down_speed(2.1, 2.5)

    assert down < 0.0
    assert error < 0.0
    assert ok is False


def test_altitude_hold_reports_ok_inside_tolerance():
    down, error, ok = altitude_hold_down_speed(2.55, 2.5)

    assert down == 0.0
    assert abs(error) <= DEFAULT_HOLD_TOLERANCE_M
    assert ok is True


def test_altitude_hold_is_inert_without_a_position_fix():
    """Non-finite AGL must command zero, not guess a vertical rate."""
    down, error, ok = altitude_hold_down_speed(float("nan"), 2.5)

    assert down == 0.0
    assert ok is False


def test_altitude_hold_respects_max_down_speed():
    """A large error must not produce an unbounded vertical command."""
    down, _, _ = altitude_hold_down_speed(20.0, 2.5, max_down_speed_m_s=0.18)

    assert down == pytest.approx(0.18)
