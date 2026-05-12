"""MapUnit tests (UC1 Map Area support)."""
import json

from scarecrow.navigation.map_unit import MapUnit


class TestMapUnit:
    def test_initial_state(self):
        m = MapUnit()
        assert m.active is False
        assert m.points == []

    def test_start_mapping_activates(self):
        m = MapUnit()
        m.start_mapping()
        assert m.active is True
        assert m.points == []

    def test_start_mapping_clears_previous_points(self, mock_lidar_scan):
        m = MapUnit()
        m.start_mapping()
        m.record_position(mock_lidar_scan(), 0, 0)
        m.start_mapping()
        assert m.points == []
        assert m.corners == []

    def test_record_position_stores_distances(self, mock_lidar_scan):
        m = MapUnit()
        m.start_mapping()
        scan = mock_lidar_scan(front=3.0, rear=7.0, left=2.0, right=5.0)
        point = m.record_position(scan, north_m=1.0, east_m=2.0)
        assert point is not None
        assert point.x == 1.0
        assert point.y == 2.0
        assert abs(point.front_dist - 3.0) < 0.5
        assert abs(point.rear_dist - 7.0) < 0.5
        assert abs(point.left_dist - 2.0) < 0.5
        assert abs(point.right_dist - 5.0) < 0.5

    def test_record_noop_when_not_active(self, mock_lidar_scan):
        m = MapUnit()
        point = m.record_position(mock_lidar_scan(), 0, 0)
        assert point is None
        assert m.points == []

    def test_finish_empty_returns_zero_area(self):
        m = MapUnit()
        m.start_mapping()
        result = m.finish_mapping()
        assert result["area_size"] == 0.0
        assert result["boundaries"] == "[]"

    def test_finish_uses_corners_for_area(self, mock_lidar_scan):
        """Area is computed from recorded corners."""
        m = MapUnit()
        m.start_mapping()
        scan = mock_lidar_scan(front=5.0, rear=5.0, left=5.0, right=5.0)
        m.record_position(scan, north_m=0.0, east_m=0.0)
        m.record_corner(0.0, 0.0)
        m.record_corner(10.0, 0.0)
        m.record_corner(10.0, 10.0)
        m.record_corner(0.0, 10.0)
        result = m.finish_mapping()
        assert abs(result["area_size"] - 100.0) < 1.0
        boundaries = json.loads(result["boundaries"])
        assert len(boundaries) == 4

    def test_finish_deactivates(self, mock_lidar_scan):
        m = MapUnit()
        m.start_mapping()
        m.record_position(mock_lidar_scan(), 0, 0)
        m.finish_mapping()
        assert m.active is False

    def test_finish_falls_back_without_corners(self, mock_lidar_scan):
        """Fallback uses wall points when no corners are recorded."""
        m = MapUnit()
        m.start_mapping()
        m.record_position(mock_lidar_scan(left=2.0, right=8.0), 0, 0)
        m.record_position(mock_lidar_scan(left=2.0, right=8.0), 5, 0)
        result = m.finish_mapping()
        boundaries = json.loads(result["boundaries"])
        assert len(boundaries) >= 2
