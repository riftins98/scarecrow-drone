from types import SimpleNamespace

from scarecrow.controllers.pursuit.entry_planner import (
    PursuitEntryAction,
    PursuitEntryPlannerConfig,
    plan_for_bearing_range,
    plan_from_observation,
)


def _target_observation(*, center_x=511.0, bbox=(497, 344, 525, 371)):
    return SimpleNamespace(
        center_x=center_x,
        center_y=357.0,
        image_width=1280.0,
        image_height=720.0,
        bbox=bbox,
    )


def test_planner_advance_for_bearing_range_matches_known_image_case():
    decision = plan_for_bearing_range(
        bearing_deg=13.5,
        range_m=8.14,
    )

    assert decision.action == PursuitEntryAction.ADVANCE
    assert abs(decision.advance_m - 5.2) < 0.2


def test_planner_can_scale_computed_advance_for_model_calibration():
    decision = plan_for_bearing_range(
        bearing_deg=13.5,
        range_m=8.14,
        config=PursuitEntryPlannerConfig(advance_scale=0.65),
    )

    assert decision.action == PursuitEntryAction.ADVANCE
    assert abs(decision.required_advance_m - 5.2) < 0.2
    assert abs(decision.advance_m - 3.4) < 0.2


def test_image_planner_entry_decision_uses_bbox_size_and_pixel_bearing():
    decision = plan_from_observation(_target_observation())

    assert decision.action == PursuitEntryAction.ADVANCE
    assert decision.reason == "advance_for_image_bearing"
    assert abs(decision.range_estimate_m - 8.14) < 0.1
    assert 4.8 < decision.advance_m < 5.6
    assert decision.entry_yaw_delta_deg == -PursuitEntryPlannerConfig().target_bearing_deg


def test_image_planner_approaches_front_target():
    decision = plan_for_bearing_range(
        bearing_deg=6.0,
        range_m=8.5,
    )

    assert decision.action == PursuitEntryAction.APPROACH
    assert decision.reason == "front_target"


def test_image_planner_rejects_narrow_non_front_side_clearance():
    decision = plan_for_bearing_range(
        bearing_deg=13.0,
        range_m=3.0,
    )

    assert decision.action == PursuitEntryAction.REJECT
    assert decision.reason == "side_clearance_too_small"
    assert decision.side_estimate_m < decision.min_safe_side_m


def test_image_planner_approaches_good_bearing():
    decision = plan_for_bearing_range(
        bearing_deg=36.0,
        range_m=4.0,
    )

    assert decision.action == PursuitEntryAction.APPROACH
    assert decision.reason == "entry_bearing"


def test_image_planner_uses_current_bearing_for_direct_approach_yaw():
    decision = plan_from_observation(
        _target_observation(center_x=690.0, bbox=(655, 344, 725, 371))
    )

    assert decision.action == PursuitEntryAction.APPROACH
    assert decision.reason == "front_target"
    assert abs(decision.entry_yaw_delta_deg - decision.camera_bearing_deg) < 0.001


def test_image_planner_rejects_missing_bbox_width():
    decision = plan_from_observation(_target_observation(bbox=None))

    assert decision.action == PursuitEntryAction.REJECT
    assert decision.reason == "invalid_range"
