"""Lidar reading validation and simple derived reads.

Moved from tests/unit/scripts/flight/ when this left the hangar flight script
for scarecrow.sensors.lidar.validation.
"""
from unittest.mock import MagicMock

from scarecrow.sensors.lidar.validation import (
    current_landing_targets,
    nearest_start_side,
    scan_valid_for_map,
    valid_distance,
)


def _lidar(scan):
    lidar = MagicMock()
    lidar.get_scan = MagicMock(return_value=scan)
    return lidar


def test_valid_distance_rejects_infinite_and_out_of_range():
    assert valid_distance(3.0) is True
    assert valid_distance(float("inf")) is False
    assert valid_distance(0.05) is False
    assert valid_distance(50.0) is False


def test_current_landing_targets_use_current_rear_left(mock_lidar_scan):
    targets = current_landing_targets(
        _lidar(mock_lidar_scan(rear=8.0, left=2.5)),
        fallback_wall_distance=2.0,
    )

    assert abs(targets.rear - 8.0) < 0.5
    assert abs(targets.left - 2.5) < 0.5


def test_current_landing_targets_fall_back_without_a_scan():
    """No scan must still yield a finite setpoint for the stabilizer."""
    targets = current_landing_targets(_lidar(None), fallback_wall_distance=2.0)

    assert targets.rear == 2.0
    assert targets.left == 2.0


def test_nearest_start_side_prefers_closer_side(mock_lidar_scan):
    assert nearest_start_side(mock_lidar_scan(left=4.0, right=8.0)) == "left"
    assert nearest_start_side(mock_lidar_scan(left=8.0, right=4.0)) == "right"


def test_scan_valid_for_map_requires_all_four_readings(mock_lidar_scan):
    """All four, not any: a partial sample projects unsupported wall hits."""
    assert scan_valid_for_map(mock_lidar_scan(front=4.0, rear=3.0, left=2.0, right=5.0))
    assert not scan_valid_for_map(
        mock_lidar_scan(front=float("inf"), rear=3.0, left=2.0, right=5.0)
    )
    assert not scan_valid_for_map(None)
