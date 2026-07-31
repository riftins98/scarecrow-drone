"""Status reporters for the hangar circuit mission.

These were four nested closures inside `run()`, each capturing mission state
through `nonlocal`. As classes they hold their own counters, which is all they
ever needed, and they become the one place that knows how flight progress is
worded.

That wording is load-bearing. `webapp/backend/services/detection_service.py`
mines these exact lines with regexes to drive the live telemetry rail -- see
`scripts/flight/CLAUDE.md` for the full list. Reformatting a line here removes
a gauge from the operator's screen and raises no error anywhere.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

from scarecrow.controllers.wall_follow import VelocityCommand
from scarecrow.util.formatting import format_altitude, format_meters


class WallFollowReporter:
    """Throttled per-leg wall-follow status, and periodic map sampling.

    Two jobs deliberately together: the status callback is the only per-tick
    hook the wall-follow loop offers, so it is also where map samples get
    scheduled. Both are rate-limited -- the loop runs at 20Hz and neither a
    human nor a boundary estimate benefits from that.
    """

    def __init__(
        self,
        *,
        leg: int,
        recorder,
        drone,
        lidar,
        altitude_ref: Mapping[str, Any],
        record_every: int = 10,
        log_every: int = 10,
    ) -> None:
        self._leg = leg
        self._recorder = recorder
        self._drone = drone
        self._lidar = lidar
        self._altitude_ref = altitude_ref
        self._record_every = record_every
        self._log_every = log_every
        self._tick = 0

    def __call__(self, result) -> None:
        self._tick += 1
        # `result.done` always reports, whatever the tick count: the final
        # state of a leg is the one line worth guaranteeing.
        if self._tick % self._log_every != 0 and not result.done:
            return
        if self._tick % self._record_every == 0 or result.done:
            self._recorder.record_sample_soon(self._drone, self._lidar)

        cmd = result.command or VelocityCommand()
        print(
            f"  [leg {self._leg} {result.elapsed_s:5.1f}s] "
            f"fwd={cmd.forward_m_s:+.2f} lat={cmd.right_m_s:+.2f} "
            f"down={cmd.down_m_s:+.2f} yaw={cmd.yawspeed_deg_s:+.1f} | "
            f"left={format_meters(result.wall_distance_m)} "
            f"front={format_meters(result.front_distance_m)} "
            f"raw_front={format_meters(result.raw_front_distance_m)} "
            f"visible={result.front_wall_visible} "
            f"{format_altitude(self._altitude_ref)}"
        )


class PursuitReporter:
    """Pursuit status, plus the one-shot "centered" frame capture.

    State transitions always print; steady approach is sampled. Losing the
    moment a pursuit went to LOST or WALL_SAFETY in a wall of routine lines is
    what makes a failed pursuit hard to explain afterwards.
    """

    # States that always print -- each marks a decision or an ending.
    IMPORTANT_STATES = frozenset(
        {"SEARCHING", "LOST", "TIMEOUT", "WALL_SAFETY", "TARGET_REACHED"}
    )

    def __init__(self, session, *, pursuit_label: str, altitude_ref: Mapping[str, Any]) -> None:
        self._session = session
        self._pursuit_label = pursuit_label
        self._altitude_ref = altitude_ref
        self._centered_requested = False

    def __call__(self, result) -> None:
        # Capture the frame at the moment the target is centred and the
        # controller commits to approaching -- the customer-facing "we found
        # it" still. Once per pursuit.
        if not self._centered_requested and result.state.value == "APPROACHING":
            self._centered_requested = True
            self._session.capture_next(f"{self._pursuit_label}_centered")
            print("  [pursuit] centered image queued before approach")

        if result.state.value not in self.IMPORTANT_STATES:
            # Roughly every 2 seconds of pursuit.
            if int(result.elapsed_s * 10) % 20 != 0:
                return

        front = format_meters(result.front_distance_m, 2)
        age = "?" if result.target_age_s is None else f"{result.target_age_s:.1f}s"
        center = (
            "?" if result.center_error_ratio is None else f"{result.center_error_ratio:.2f}"
        )
        vertical = (
            "?"
            if result.vertical_error_ratio is None
            else f"{result.vertical_error_ratio:+.2f}"
        )
        print(
            f"  [{result.elapsed_s:5.1f}s] {result.state.value} "
            f"front={front} age={age} center_err={center} vert_err={vertical} "
            f"down={result.command.down_m_s:+.2f} yaw={result.command.yawspeed_deg_s:+.1f} "
            f"{format_altitude(self._altitude_ref)} reason={result.reason}"
        )


def report_search_status(event: str, data: dict[str, object]) -> None:
    """Narrate the pursuit controller's relocalisation sweep.

    Stateless -- the controller supplies everything. Kept as a function so it
    can be passed directly as `on_search_status`.
    """
    if event == "start":
        front = data.get("front_distance_m")
        age = data.get("target_age_s")
        front_text = "?" if front is None else f"{float(front):.2f}m"
        age_text = "?" if age is None else f"{float(age):.1f}s"
        print(
            "  [search] target lost; starting sweep "
            f"front={front_text} last_age={age_text}"
        )
    elif event == "hover":
        print("  [search] hover before relocalization")
    elif event == "sweep_start":
        print(
            "  [search] sweep "
            f"{data.get('direction')} "
            f"angle={float(data['angle_deg']):.1f}deg "
            f"yaw={float(data['yaw_speed_deg_s']):+.1f}deg/s "
            f"duration={float(data['duration_s']):.1f}s"
        )
    elif event == "sweep_reacquired":
        print(f"  [search] target reacquired during {data.get('direction')} sweep")
    elif event == "sweep_end":
        print(f"  [search] sweep {data.get('direction')} ended found={data.get('found')}")
    elif event == "reacquired":
        print("  [search] relocalization complete; resuming pursuit")
    elif event == "wall_safety_abort":
        print(
            "  [search] abort: wall safety "
            f"left={float(data['left_distance_m']):.2f}m "
            f"right={float(data['right_distance_m']):.2f}m"
        )
    elif event == "failed":
        print("  [search] relocalization failed; pursuit will end safely")


class LandingReporter:
    """Landing status: throttle the descent, always print the outcome."""

    def __init__(self, *, log_every: int = 10) -> None:
        self._log_every = log_every
        self._tick = 0

    def __call__(self, result) -> None:
        self._tick += 1
        agl = format_meters(result.final_agl_m, 2)
        if result.reason == "descending":
            if self._tick % self._log_every != 0:
                return
            print(f"  [landing] descending agl={agl}")
            return
        print(
            f"  [landing] {result.reason} agl={agl} "
            f"touchdown={result.touchdown_confirmed} disarmed={result.disarmed}"
        )


def report_planner_decision(decision, *, advance_scale: float) -> None:
    """Print the pursuit-entry planner's image geometry and verdict."""
    advance = (
        decision.advance_m
        if math.isfinite(decision.advance_m)
        else decision.required_advance_m
    )
    print(
        "  [planner] image geometry: "
        f"bbox_w={decision.bbox_width_px:.0f}px "
        f"bearing={decision.bearing_deg:.1f}deg "
        f"signed={decision.camera_bearing_deg:+.1f}deg "
        f"range_est={format_meters(decision.range_estimate_m)} "
        f"side_est={format_meters(decision.side_estimate_m)} "
        f"forward_est={format_meters(decision.forward_estimate_m)} "
        f"target_bearing={decision.target_bearing_deg:.1f}deg "
        f"advance={format_meters(advance)} "
        f"required_advance={format_meters(decision.required_advance_m)} "
        f"advance_scale={advance_scale:.2f} "
        f"decision={decision.action.value}:{decision.reason}"
    )
