"""Pre-pursuit entry planner from camera target geometry."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class PursuitEntryAction(str, Enum):
    """Planner decision for how to enter target pursuit."""

    APPROACH = "approach"
    ADVANCE = "advance"
    REJECT = "reject"


@dataclass(frozen=True)
class PursuitEntryPlannerConfig:
    """Camera geometry and safety thresholds for pursuit entry planning."""

    camera_horizontal_fov_rad: float = 1.74
    target_bearing_deg: float = 35.0
    direct_front_bearing_deg: float = 12.0
    range_width_px_m: float = 228.0
    min_bbox_width_px: float = 4.0
    side_clearance_min_m: float = 1.5
    side_clearance_buffer_m: float = 0.1
    max_advance_m: float = 8.0
    advance_scale: float = 1.0


@dataclass(frozen=True)
class PursuitEntryPlan:
    """Result of a pursuit-entry planning pass."""

    action: PursuitEntryAction
    reason: str
    bearing_deg: float = math.nan
    signed_bearing_deg: float = math.nan
    camera_bearing_deg: float = math.nan
    range_estimate_m: float = math.nan
    side_estimate_m: float = math.nan
    forward_estimate_m: float = math.nan
    target_bearing_deg: float = math.nan
    min_safe_side_m: float = math.nan
    target_forward_m: float = math.nan
    required_advance_m: float = math.nan
    advance_m: float = math.nan
    entry_yaw_delta_deg: float = math.nan
    bbox_width_px: float = math.nan
    max_advance_m: float = math.nan


def camera_bearing_deg(
    observation,
    config: PursuitEntryPlannerConfig | None = None,
) -> float:
    """Return horizontal target bearing in camera pixels, positive to the right."""
    cfg = config or PursuitEntryPlannerConfig()
    if observation.image_width <= 0.0 or not math.isfinite(observation.image_width):
        return math.nan
    focal_px = observation.image_width / (
        2.0 * math.tan(cfg.camera_horizontal_fov_rad / 2.0)
    )
    image_cx = observation.image_width / 2.0
    return math.degrees(math.atan2(observation.center_x - image_cx, focal_px))


def bbox_width_px(observation) -> float:
    """Return the target bbox width in pixels, or NaN when unavailable."""
    bbox = getattr(observation, "bbox", None)
    if not bbox or len(bbox) != 4:
        return math.nan
    x1, _, x2, _ = bbox
    width_px = abs(float(x2) - float(x1))
    return width_px if math.isfinite(width_px) else math.nan


def image_range_estimate_m(
    observation,
    config: PursuitEntryPlannerConfig | None = None,
) -> float:
    """Estimate range from calibrated target bbox width."""
    cfg = config or PursuitEntryPlannerConfig()
    width_px = bbox_width_px(observation)
    if width_px < cfg.min_bbox_width_px:
        return math.nan
    return cfg.range_width_px_m / width_px


def plan_for_bearing_range(
    *,
    bearing_deg: float,
    range_m: float,
    config: PursuitEntryPlannerConfig | None = None,
) -> PursuitEntryPlan:
    """Plan pursuit entry from a signed camera bearing and estimated range."""
    cfg = config or PursuitEntryPlannerConfig()
    bearing_abs = abs(bearing_deg)
    if not math.isfinite(bearing_abs) or bearing_abs <= 0.0:
        return PursuitEntryPlan(
            action=PursuitEntryAction.REJECT,
            reason="invalid_bearing",
        )
    if not math.isfinite(range_m) or range_m <= 0.0:
        return PursuitEntryPlan(
            action=PursuitEntryAction.REJECT,
            reason="invalid_range",
            bearing_deg=bearing_abs,
            signed_bearing_deg=bearing_deg,
        )

    min_safe_side_m = cfg.side_clearance_min_m + cfg.side_clearance_buffer_m
    bearing_rad = math.radians(bearing_abs)
    side_estimate_m = range_m * math.sin(bearing_rad)
    forward_estimate_m = range_m * math.cos(bearing_rad)
    common = {
        "bearing_deg": bearing_abs,
        "signed_bearing_deg": bearing_deg,
        "range_estimate_m": range_m,
        "side_estimate_m": side_estimate_m,
        "forward_estimate_m": forward_estimate_m,
        "target_bearing_deg": cfg.target_bearing_deg,
        "min_safe_side_m": min_safe_side_m,
    }

    if bearing_abs <= cfg.direct_front_bearing_deg:
        return PursuitEntryPlan(
            action=PursuitEntryAction.APPROACH,
            reason="front_target",
            **common,
        )

    if side_estimate_m < min_safe_side_m:
        return PursuitEntryPlan(
            action=PursuitEntryAction.REJECT,
            reason="side_clearance_too_small",
            **common,
        )

    if bearing_abs >= cfg.target_bearing_deg:
        return PursuitEntryPlan(
            action=PursuitEntryAction.APPROACH,
            reason="entry_bearing",
            **common,
        )

    target_forward_m = side_estimate_m / math.tan(math.radians(cfg.target_bearing_deg))
    required_advance_m = max(0.0, forward_estimate_m - target_forward_m)
    advance_m = required_advance_m * max(0.0, cfg.advance_scale)

    if advance_m <= 0.0:
        return PursuitEntryPlan(
            action=PursuitEntryAction.REJECT,
            reason="no_valid_forward_advance",
            target_forward_m=target_forward_m,
            required_advance_m=required_advance_m,
            **common,
        )

    if advance_m > cfg.max_advance_m:
        return PursuitEntryPlan(
            action=PursuitEntryAction.REJECT,
            reason="advance_too_large",
            target_forward_m=target_forward_m,
            required_advance_m=required_advance_m,
            max_advance_m=cfg.max_advance_m,
            **common,
        )

    return PursuitEntryPlan(
        action=PursuitEntryAction.ADVANCE,
        reason="advance_for_image_bearing",
        target_forward_m=target_forward_m,
        required_advance_m=required_advance_m,
        advance_m=advance_m,
        **common,
    )


def plan_from_observation(
    observation,
    config: PursuitEntryPlannerConfig | None = None,
) -> PursuitEntryPlan:
    """Plan pursuit entry from the latest target observation."""
    cfg = config or PursuitEntryPlannerConfig()
    bearing = camera_bearing_deg(observation, cfg)
    range_m = image_range_estimate_m(observation, cfg)
    plan = plan_for_bearing_range(
        bearing_deg=bearing,
        range_m=range_m,
        config=cfg,
    )
    entry_yaw_delta = math.nan
    if math.isfinite(bearing):
        if plan.action == PursuitEntryAction.ADVANCE:
            direction = 1.0 if bearing >= 0.0 else -1.0
            entry_yaw_delta = direction * plan.target_bearing_deg
        else:
            entry_yaw_delta = bearing

    return PursuitEntryPlan(
        **{
            **plan.__dict__,
            "camera_bearing_deg": bearing,
            "entry_yaw_delta_deg": entry_yaw_delta,
            "bbox_width_px": bbox_width_px(observation),
        }
    )


__all__ = [
    "PursuitEntryAction",
    "PursuitEntryPlan",
    "PursuitEntryPlannerConfig",
    "bbox_width_px",
    "camera_bearing_deg",
    "image_range_estimate_m",
    "plan_for_bearing_range",
    "plan_from_observation",
]
