"""Every tunable for the hangar circuit pursuit mission, in one place.

These were 40-odd module-level constants in the flight script, interleaved with
code and impossible to override without editing the file. As a dataclass they
can be constructed per run, logged, and unit-tested against.

The values are unchanged from the tuned script -- this is a move, not a
retune. Each group notes what it controls and why it is set where it is.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from scarecrow.controllers.pursuit import PursuitEntryPlannerConfig

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


@dataclass
class HangarCircuitConfig:
    """Mission parameters. Defaults match the tuned hangar configuration."""

    # -- connection ----------------------------------------------------
    system_address: str = "udp://:14540"

    # -- mission shape -------------------------------------------------
    wall_distance_m: float = 2.0
    target_distance_m: float = 1.5
    start_side: str = "left"
    max_legs: int = 4
    leg_timeout_s: float = 300.0
    hover_seconds: float = 5.0

    # -- altitude ------------------------------------------------------
    # None = derive from the upward rangefinder (ceiling minus clearance).
    target_alt_m: float | None = None
    ceiling_clearance_m: float | None = None

    # -- detection -----------------------------------------------------
    # Two thresholds by design. Scanning is strict because a false positive
    # costs an entire pursuit detour; pursuit is permissive because losing a
    # confirmed target costs an abort and a return-to-entry.
    yolo_model_path: str = os.path.join(REPO_ROOT, "models", "yolo", "yolov8s.pt")
    scan_confidence: float = 0.70
    pursuit_confidence: float = 0.45
    image_width_px: int = 1280
    target_classes: tuple[str, ...] = ("bird", "pigeon")

    # -- target removal ------------------------------------------------
    # A reached target is deleted from the Gazebo world so the mission does not
    # immediately re-detect the bird it just dispersed.
    target_model_prefixes: tuple[str, ...] = ("pigeon",)
    target_uri_keywords: tuple[str, ...] = ("pigeon",)

    # -- pursuit -------------------------------------------------------
    pursuit_timeout_s: float = 75.0
    max_pursuit_attempts: int = 2

    # -- pursuit entry planner -----------------------------------------
    # advance_scale < 1 deliberately under-shoots the computed advance: the
    # range estimate comes from bbox width and is optimistic, and stopping
    # short keeps the target in frame where overshooting loses it entirely.
    entry_advance_scale: float = 0.65
    planner_advance_timeout_s: float = 60.0
    planner_reacquire_timeout_s: float = 4.0
    # Entry yaw is slow on purpose -- fast rotation smears the target across
    # frames and YOLO stops detecting it mid-turn.
    planner_entry_yaw_speed_deg_s: float = 6.0
    planner_entry_yaw_min_speed_deg_s: float = 2.0
    planner_entry_yaw_center_bearing_deg: float = 30.0

    # -- wall follow ---------------------------------------------------
    wall_follow_speed_m_s: float = 0.30
    wall_follow_kp: float = 0.75
    wall_follow_kd: float = 0.22
    wall_follow_max_lateral_m_s: float = 0.24
    wall_follow_yaw_kp: float = 2.0
    wall_follow_max_yaw_deg_s: float = 8.0

    # -- altitude hold -------------------------------------------------
    altitude_hold_kp: float = 0.45
    altitude_hold_tolerance_m: float = 0.12
    altitude_hold_max_down_speed_m_s: float = 0.18
    altitude_warning_error_m: float = 0.20

    # -- rotation ------------------------------------------------------
    rotate_timeout_s: float = 25.0
    rotate_tolerance_deg: float = 5.0

    # -- mapping -------------------------------------------------------
    map_record_every: int = 10
    route_sample_interval_s: float = 1.0

    # -- output --------------------------------------------------------
    flight_id: str | None = None
    output_root: str = os.path.join(REPO_ROOT, "webapp", "output")

    entry_planner: PursuitEntryPlannerConfig = field(init=False)

    def __post_init__(self) -> None:
        self.entry_planner = PursuitEntryPlannerConfig(
            advance_scale=self.entry_advance_scale,
        )

    @property
    def output_dir(self) -> str:
        return os.path.join(self.output_root, self.flight_id or "unknown")
