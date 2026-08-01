"""The lateral PD must behave the same at any loop rate.

The derivative used to be a raw per-call difference with no reference to
elapsed time, so its damping scaled with however fast the loop ran. That was
latent until the telemetry cache tripled the loop rate (7Hz -> ~20Hz), which
would have cut the kd contribution to a third and turned a fixed yaw
oscillation into a new lateral one.
"""
import time

from scarecrow.controllers.wall_follow import (
    MAX_DT_S,
    NOMINAL_DT_S,
    WallFollowController,
)


def _controller():
    return WallFollowController(
        side="left", target_distance=2.0, kp=0.75, kd=0.22, max_lateral_speed=10.0
    )


def _step(ctrl, wall_dist):
    return ctrl.update(wall_dist=wall_dist, front_dist=9.0, wall_angle_error=0.0)


KP = 0.75


def _damping_term(dt: float, error_rate_m_s: float) -> float:
    """Isolate the derivative contribution at a given loop rate.

    The proportional term is subtracted out: two loops running at different
    rates necessarily observe different *positions* after one tick, so their
    P terms differ legitimately. What must NOT differ is the damping produced
    by the same physical rate of change.
    """
    change = error_rate_m_s * dt
    ctrl = _controller()
    _step(ctrl, 2.0)
    time.sleep(dt)
    lateral = abs(_step(ctrl, 2.0 + change).right_m_s)
    return lateral - KP * change


def test_same_error_rate_gives_same_damping_at_different_loop_rates():
    """A 20Hz loop and a 7Hz loop seeing the same drift rate damp it equally.

    At 7Hz the error moves ~3x further per tick than at 20Hz, so a raw
    per-call difference reports 3x the derivative for identical physical
    motion -- which is exactly the bug this normalisation removes.
    """
    fast = _damping_term(0.05, 1.0)   # 20 Hz
    slow = _damping_term(0.15, 1.0)   # ~7 Hz, the rate actually measured

    assert abs(fast - slow) < 0.005, (
        f"damping still depends on loop rate: {fast:.4f} vs {slow:.4f}"
    )


def test_derivative_opposes_growing_error():
    """Damping must push back against motion away from the target."""
    ctrl = _controller()
    _step(ctrl, 2.0)
    time.sleep(NOMINAL_DT_S)
    moving_away = _step(ctrl, 2.30).right_m_s

    ctrl2 = _controller()
    _step(ctrl2, 2.30)
    time.sleep(NOMINAL_DT_S)
    holding = _step(ctrl2, 2.30).right_m_s

    # Same position error, but one is actively drifting: it must get more
    # correction than the one sitting still.
    assert abs(moving_away) > abs(holding)


def test_first_call_has_no_derivative_kick():
    """With no previous sample there is no rate to compute."""
    ctrl = _controller()
    cmd = _step(ctrl, 2.50)

    # Pure proportional: sign * kp * error, with kp=0.75 and error=0.50.
    assert abs(abs(cmd.right_m_s) - 0.375) < 1e-6


def test_a_stalled_tick_does_not_produce_a_derivative_kick():
    """A long gap is a stall, not a fast movement.

    Without the guard, one blocked tick would divide a normal error change by
    a tiny nominal/dt ratio -- or worse, a resumed loop would amplify a stale
    sample into a large spurious correction.
    """
    ctrl = _controller()
    _step(ctrl, 2.0)
    time.sleep(MAX_DT_S + 0.05)
    stalled = _step(ctrl, 2.30).right_m_s

    ctrl2 = _controller()
    proportional_only = _step(ctrl2, 2.30).right_m_s

    assert abs(stalled - proportional_only) < 1e-6
