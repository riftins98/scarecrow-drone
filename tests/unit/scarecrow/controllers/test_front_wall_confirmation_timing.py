"""Front-wall confirmation must be a duration, not a call count.

This detector exists to reject a spurious front reading by requiring it to
persist -- and "persist" only means something in time. Counting update() calls
tied it to the caller's loop rate.

It failed exactly that way: caching PX4 telemetry took the wall-follow loop
from 7.0Hz to 12.8Hz, halving the confirmation window from 571ms to 312ms. The
detector confirmed a wall that was not there, the leg stopped with 8.1m of open
space ahead, and the corner turn that followed had nothing to align against.
"""
import time

import numpy as np
import pytest

from scarecrow.controllers.front_wall_detector import FrontWallDetector


@pytest.fixture
def wall_scan(mock_lidar_scan):
    """A scan with a solid wall 1.5m ahead, inside a 2.0m stop distance."""
    return mock_lidar_scan(front=1.5, rear=8.0, left=2.0, right=8.0)


def _confirm_after(detector, scan, *, calls: int, interval_s: float) -> bool:
    for _ in range(calls):
        state = detector.update(scan)
        if state.stop_confirmed:
            return True
        time.sleep(interval_s)
    return detector.update(scan).stop_confirmed


def test_confirmation_window_is_the_same_at_any_loop_rate():
    """The wall is confirmed after the same elapsed time, not the same tick count."""
    detector = FrontWallDetector(stop_distance_m=2.0, confirm_seconds=0.20)
    assert detector.confirm_seconds == 0.20


def test_a_fast_loop_does_not_confirm_early(wall_scan):
    """The regression: at 12.8Hz, 4 ticks is only 312ms of evidence.

    A high-rate caller must still wait out the full window, or a transient
    reflection is enough to stop a leg in open space.
    """
    detector = FrontWallDetector(stop_distance_m=2.0, confirm_seconds=0.30)

    # 5 rapid calls -- more than the old 4-cycle threshold, but ~50ms total.
    confirmed_early = any(
        detector.update(wall_scan).stop_confirmed for _ in range(5)
    )

    assert not confirmed_early, "confirmed on tick count, not elapsed time"


def test_the_window_does_elapse(wall_scan):
    detector = FrontWallDetector(stop_distance_m=2.0, confirm_seconds=0.10)
    detector.update(wall_scan)
    time.sleep(0.15)

    assert detector.update(wall_scan).stop_confirmed


def test_a_gap_in_evidence_restarts_the_window(wall_scan, mock_lidar_scan):
    """Confirmation requires CONTINUOUS evidence, not cumulative."""
    clear = mock_lidar_scan(front=9.0, rear=8.0, left=2.0, right=8.0)
    detector = FrontWallDetector(stop_distance_m=2.0, confirm_seconds=0.15)

    detector.update(wall_scan)
    time.sleep(0.10)
    detector.update(clear)          # wall disappears -- restart
    time.sleep(0.10)

    assert not detector.update(wall_scan).stop_confirmed


def test_legacy_confirm_cycles_is_converted():
    """Callers passing the old int still get an equivalent window."""
    detector = FrontWallDetector(stop_distance_m=2.0, confirm_cycles=4)

    # 4 cycles at the 7Hz the value was tuned against.
    assert abs(detector.confirm_seconds - 4 / 7.0) < 1e-6
