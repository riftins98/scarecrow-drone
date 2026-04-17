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

    def test_finish_computes_bounding_box(self, mock_lidar_scan):
        """Simulate flying a 10x10 room, sampling at center. Walls 5m in each direction."""
        m = MapUnit()
        m.start_mapping()
        scan = mock_lidar_scan(front=5.0, rear=5.0, left=5.0, right=5.0)
        m.record_position(scan, north_m=0.0, east_m=0.0)
        result = m.finish_mapping()
        # Bounding box should be 10x10 = 100 sq m
        assert abs(result["area_size"] - 100.0) < 1.0
        boundaries = json.loads(result["boundaries"])
        assert len(boundaries) == 4

    def test_finish_deactivates(self, mock_lidar_scan):
        m = MapUnit()
        m.start_mapping()
        m.record_position(mock_lidar_scan(), 0, 0)
        m.finish_mapping()
        assert m.active is False

    def test_multi_point_envelope(self, mock_lidar_scan):
        """Record at two positions -- envelope should span both."""
        m = MapUnit()
        m.start_mapping()
        # At (0,0): walls 2m left, 8m right
        m.record_position(mock_lidar_scan(left=2.0, right=8.0), 0, 0)
        # At (5,0): walls 2m left, 8m right still
        m.record_position(mock_lidar_scan(left=2.0, right=8.0), 5, 0)
        result = m.finish_mapping()
        boundaries = json.loads(result["boundaries"])
        ys = [p["y"] for p in boundaries]
        # Envelope spans from -2 (left of 0) to +8 (right of 0, also right of 5)
        assert min(ys) == -2.0
        assert max(ys) == 8.0
