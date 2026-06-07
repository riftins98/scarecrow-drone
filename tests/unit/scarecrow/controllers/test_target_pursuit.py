from scarecrow.controllers.pursuit import (
    TargetObservation,
    TargetPursuitConfig,
    TargetPursuitController,
    TargetPursuitState,
)


def _observation(center_x=640.0, center_y=360.0, now=100.0):
    """Build a target observation centered in a 1280x720 frame by default."""
    return TargetObservation(
        center_x=center_x,
        center_y=center_y,
        image_width=1280.0,
        image_height=720.0,
        confidence=0.9,
        timestamp=now,
    )


def test_target_left_and_right_produce_yaw_signs(mock_lidar_scan):
    scan = mock_lidar_scan(front=5.0, left=2.0, right=8.0)

    left = TargetPursuitController()
    left_result = left.update(scan, _observation(center_x=400.0), now=100.0)
    assert left_result.state == TargetPursuitState.ALIGNING
    assert left_result.command.yawspeed_deg_s < 0

    right = TargetPursuitController()
    right_result = right.update(scan, _observation(center_x=900.0), now=100.0)
    assert right_result.state == TargetPursuitState.ALIGNING
    assert right_result.command.yawspeed_deg_s > 0


def test_centered_target_approaches_forward(mock_lidar_scan):
    scan = mock_lidar_scan(front=5.0, left=2.0, right=8.0)
    controller = TargetPursuitController()

    result = controller.update(scan, _observation(center_x=640.0), now=100.0)

    assert result.state == TargetPursuitState.APPROACHING
    assert result.command.forward_m_s > 0
    assert result.command.yawspeed_deg_s == 0
    assert result.command.down_m_s == 0


def test_target_high_in_frame_commands_climb(mock_lidar_scan):
    """Verify a high target in the frame commands upward pursuit motion."""
    scan = mock_lidar_scan(front=5.0, left=2.0, right=8.0)
    controller = TargetPursuitController()

    result = controller.update(scan, _observation(center_y=180.0), now=100.0)

    assert result.state == TargetPursuitState.ALIGNING
    assert result.command.yawspeed_deg_s == 0
    assert result.command.down_m_s < 0
    assert result.vertical_error_ratio is not None
    assert result.vertical_error_ratio < 0


def test_target_low_in_frame_commands_descent(mock_lidar_scan):
    """Verify a low target in the frame commands downward pursuit motion."""
    scan = mock_lidar_scan(front=5.0, left=2.0, right=8.0)
    controller = TargetPursuitController()

    result = controller.update(scan, _observation(center_y=540.0), now=100.0)

    assert result.state == TargetPursuitState.ALIGNING
    assert result.command.yawspeed_deg_s == 0
    assert result.command.down_m_s > 0
    assert result.vertical_error_ratio is not None
    assert result.vertical_error_ratio > 0


def test_front_distance_at_target_stops_successfully(mock_lidar_scan):
    scan = mock_lidar_scan(front=1.0, left=2.0, right=8.0)
    controller = TargetPursuitController(TargetPursuitConfig(target_distance_m=1.5))

    result = controller.update(scan, _observation(), now=100.0)

    assert result.done
    assert result.reached_target
    assert result.state == TargetPursuitState.TARGET_REACHED
    assert result.command.is_zero


def test_target_reached_takes_priority_over_side_wall_safety(mock_lidar_scan):
    scan = mock_lidar_scan(front=1.4, left=0.4, right=8.0)
    controller = TargetPursuitController(
        TargetPursuitConfig(target_distance_m=1.5, min_wall_distance_m=0.8)
    )

    result = controller.update(scan, _observation(), now=100.0)

    assert result.done
    assert result.reached_target
    assert result.state == TargetPursuitState.TARGET_REACHED


def test_missing_target_transitions_to_search(mock_lidar_scan):
    scan = mock_lidar_scan(front=5.0, left=2.0, right=8.0)
    controller = TargetPursuitController(
        TargetPursuitConfig(detection_miss_count_required=2)
    )

    controller.update(scan, None, now=100.0)
    result = controller.update(scan, None, now=100.1)

    assert result.state == TargetPursuitState.SEARCHING
    assert result.reason == "target_missing"


def test_side_wall_too_close_returns_wall_safety(mock_lidar_scan):
    scan = mock_lidar_scan(front=5.0, left=0.4, right=8.0)
    controller = TargetPursuitController(
        TargetPursuitConfig(min_wall_distance_m=0.8)
    )

    result = controller.update(scan, _observation(), now=100.0)

    assert result.done
    assert result.state == TargetPursuitState.WALL_SAFETY
    assert result.reason == "wall_safety"
