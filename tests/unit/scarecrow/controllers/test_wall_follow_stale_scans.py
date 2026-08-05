"""The wall-follow derivative must advance on scans, not on calls.

The loop runs at ~20Hz. In simulation the lidar publishes at 30Hz, so almost
every call gets a fresh scan and per-call differencing is indistinguishable
from per-sample. A real RPLidar A1M8 spins at roughly 5.5Hz, so on the drone
about three calls in four read the same scan back — and a derivative measured
per call then reads zero, zero, zero, spike.

That is not a damping term, it drives. These tests are written from the
hardware's rate, because the simulator cannot currently produce the failure.
"""
import pytest

from scarecrow.controllers.wall_follow import (
    MAX_DT_S,
    NOMINAL_DT_S,
    WallFollowController,
)


def _controller(**kw):
    kw.setdefault("side", "left")
    kw.setdefault("target_distance", 2.0)
    kw.setdefault("front_stop_distance", 1.0)
    return WallFollowController(**kw)


#: 20Hz control loop reading a 5.5Hz lidar: a fresh scan roughly every 4th call.
LOOP_DT = 0.05
SCAN_DT = 0.18


class TestStaleScansHoldTheDerivative:
    def test_a_repeated_scan_does_not_report_zero_rate_of_change(self):
        """Zero would tell the controller the error is steady when it is not."""
        c = _controller()
        c.update(2.00, 9.0, sample_time=0.00)
        c.update(2.06, 9.0, sample_time=SCAN_DT)
        moving = c._last_d_error
        assert moving != 0.0

        c.update(2.06, 9.0, sample_time=SCAN_DT)   # same scan, next loop tick

        assert c._last_d_error == pytest.approx(moving), \
            "a repeated scan reset the derivative to zero"

    def test_a_repeated_scan_produces_the_same_command(self):
        """Nothing new was measured, so nothing should change."""
        c = _controller()
        c.update(2.00, 9.0, sample_time=0.00)
        first = c.update(2.06, 9.0, sample_time=SCAN_DT)
        repeat = c.update(2.06, 9.0, sample_time=SCAN_DT)

        assert repeat.right_m_s == pytest.approx(first.right_m_s)

    def test_the_derivative_uses_the_scan_interval_not_the_call_interval(self):
        """The bug: four ticks of change divided by one tick of dt.

        Three stale reads then a fresh one must be differentiated over the
        0.18s between scans, not the 0.05s between calls — otherwise the
        derivative comes out ~3.6x too large exactly when the drone is moving.
        """
        c = _controller()
        c.update(2.00, 9.0, sample_time=0.00)
        for _ in range(3):
            c.update(2.00, 9.0, sample_time=0.00)      # stale repeats
        c.update(2.06, 9.0, sample_time=SCAN_DT)       # fresh

        expected = 0.06 * (NOMINAL_DT_S / SCAN_DT)
        assert c._last_d_error == pytest.approx(expected, rel=1e-6)

    def test_stale_reads_do_not_accumulate_into_a_spike(self):
        """The failing direction: repeats must never inflate the correction."""
        c = _controller()
        c.update(2.00, 9.0, sample_time=0.00)
        c.update(2.06, 9.0, sample_time=SCAN_DT)
        healthy = abs(c.update(2.06, 9.0, sample_time=SCAN_DT).right_m_s)

        for _ in range(10):
            cmd = c.update(2.06, 9.0, sample_time=SCAN_DT)

        assert abs(cmd.right_m_s) <= healthy + 1e-9


class TestSlowSensorMatchesFastSensor:
    """Same physical motion, two sensor rates, comparable damping."""

    def test_a_5hz_lidar_and_a_30hz_lidar_agree_on_the_rate_of_change(self):
        fast = _controller()
        slow = _controller()

        # 30Hz sensor, read every loop tick.
        t, dist = 0.0, 2.00
        for _ in range(12):
            t += 1 / 30.0
            dist += 0.01
            fast.update(dist, 9.0, sample_time=t)

        # 5.5Hz sensor, same motion, read at 20Hz so most reads are repeats.
        t, dist, tick = 0.0, 2.00, 0.0
        for _ in range(12):
            t += SCAN_DT
            dist += 0.01 * (SCAN_DT * 30.0)     # same metres per second
            for _ in range(4):
                tick += LOOP_DT
                slow.update(dist, 9.0, sample_time=t)

        # Recover the rate of change from the normalised derivative. Both
        # controllers saw the same metres-per-second, so they should agree
        # regardless of how often their sensor reported it.
        fast_rate = fast._last_d_error / NOMINAL_DT_S
        slow_rate = slow._last_d_error / NOMINAL_DT_S
        assert slow_rate == pytest.approx(fast_rate, rel=0.35)


class TestBackwardCompatibility:
    def test_callers_without_a_sample_time_keep_the_old_behaviour(self):
        """Callers holding only a distance must keep working.

        Per-call differencing is correct whenever the sensor outpaces the loop,
        which is every simulation run today.
        """
        c = _controller()
        c.update(2.00, 9.0)
        cmd = c.update(2.06, 9.0)

        assert isinstance(cmd.right_m_s, float)

    def test_reset_clears_the_held_derivative(self):
        """A new leg must not inherit the last leg's rate of change."""
        c = _controller()
        c.update(2.00, 9.0, sample_time=0.00)
        c.update(2.20, 9.0, sample_time=SCAN_DT)
        assert c._last_d_error != 0.0

        c.reset()

        assert c._last_d_error == 0.0
        assert c._prev_error is None

    def test_a_long_gap_between_scans_is_ignored(self):
        """A stalled sensor must not become one enormous derivative kick."""
        c = _controller()
        c.update(2.00, 9.0, sample_time=0.00)
        c.update(2.50, 9.0, sample_time=MAX_DT_S + 1.0)

        assert c._last_d_error == 0.0

    def test_time_going_backwards_is_treated_as_stale(self):
        """Sim resets and clock jumps must not produce a negative dt."""
        c = _controller()
        c.update(2.00, 9.0, sample_time=5.00)
        c.update(2.10, 9.0, sample_time=5.18)
        held = c._last_d_error

        c.update(2.30, 9.0, sample_time=1.00)   # clock jumped backwards

        assert c._last_d_error == pytest.approx(held)
