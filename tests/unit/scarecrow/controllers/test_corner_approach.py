import pytest

from scarecrow.controllers.corner_approach import CornerApproachController


def test_left_corner_corrects_both_axes_when_both_distances_are_too_far(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=5.0, left=5.0)).command

    assert cmd.forward_m_s < 0.0
    assert cmd.right_m_s < 0.0


def test_left_corner_moves_toward_side_after_rear_is_in_zone(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        tolerance=0.2,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=3.1, left=5.0)).command

    assert cmd.forward_m_s == 0.0
    assert cmd.right_m_s < 0.0


def test_left_corner_stops_side_motion_once_at_target_zone(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        tolerance=0.2,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=5.0, left=2.9)).command

    assert cmd.forward_m_s < 0.0
    assert cmd.right_m_s == 0.0


def test_left_corner_moves_away_when_side_is_too_close(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        tolerance=0.2,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=3.0, left=2.6)).command

    assert cmd.forward_m_s == 0.0
    assert cmd.right_m_s > 0.0


def test_left_corner_brakes_when_side_is_closing_fast_near_target(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        tolerance=0.2,
        brake_margin=1.0,
        brake_rate_m_s=0.15,
    )

    ctrl.update(mock_lidar_scan(rear=3.0, left=4.0), now=0.0)
    cmd = ctrl.update(mock_lidar_scan(rear=3.0, left=3.1), now=1.0).command

    assert cmd.forward_m_s == 0.0
    assert cmd.right_m_s > 0.0


def test_rear_too_close_corrects_away_while_still_countering_side_error(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        tolerance=0.2,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=2.6, left=5.0)).command

    assert cmd.forward_m_s > 0.0
    assert cmd.right_m_s < 0.0


def test_total_speed_is_capped_for_diagonal_motion(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        max_forward_speed=0.2,
        max_lateral_speed=0.2,
        max_total_speed=0.16,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=5.0, left=5.0)).command

    assert (cmd.forward_m_s**2 + cmd.right_m_s**2) ** 0.5 <= 0.1601


def test_right_corner_moves_right_when_right_side_is_too_far(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="right",
        rear_distance=3.0,
        side_distance=3.0,
    )

    cmd = ctrl.update(mock_lidar_scan(rear=3.0, right=5.0)).command

    assert cmd.forward_m_s == 0.0
    assert cmd.right_m_s > 0.0


def test_reports_done_after_settling_in_zone(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        tolerance=0.2,
        stable_time=0.5,
    )
    scan = mock_lidar_scan(rear=3.1, left=2.9)

    first = ctrl.update(scan, now=0.0)
    second = ctrl.update(scan, now=0.6)

    assert first.reason == "settling"
    assert second.done is True
    assert ctrl.done is True


def test_reports_unsafe_when_clearance_too_close(mock_lidar_scan):
    ctrl = CornerApproachController(
        side="left",
        rear_distance=3.0,
        side_distance=3.0,
        min_clearance=1.0,
    )

    result = ctrl.update(mock_lidar_scan(rear=3.0, left=0.8))

    assert result.unsafe is True
    assert result.reason == "unsafe_clearance"
    assert result.command.is_zero


def test_rejects_invalid_side():
    with pytest.raises(ValueError):
        CornerApproachController(
            side="center",
            rear_distance=3.0,
            side_distance=3.0,
        )
