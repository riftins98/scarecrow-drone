"""UT-06..07: FrontWallDetector tests (ADD Section 5.4)."""
from scarecrow.controllers.front_wall_detector import FrontWallDetector


class TestFrontWallDetector:
    def test_no_stop_on_first_cycle(self, mock_lidar_scan):
        """UT-06: Requires confirm_cycles consecutive detections before stopping."""
        det = FrontWallDetector(stop_distance_m=3.0, confirm_cycles=3)
        scan = mock_lidar_scan(front=2.0)
        state = det.update(scan)
        assert not state.stop_confirmed

    def test_confirms_after_n_cycles(self, mock_lidar_scan):
        """UT-07: Stop confirmed after confirm_cycles consecutive detections."""
        det = FrontWallDetector(stop_distance_m=3.0, confirm_cycles=2)
        scan = mock_lidar_scan(front=2.0)
        det.update(scan)
        state = det.update(scan)
        assert state.stop_confirmed

    def test_counter_resets_on_clear(self, mock_lidar_scan):
        """If front clears, counter resets -- needs full N cycles again."""
        det = FrontWallDetector(stop_distance_m=3.0, confirm_cycles=3)
        near = mock_lidar_scan(front=2.0)
        far = mock_lidar_scan(front=8.0)
        det.update(near)
        det.update(near)
        det.update(far)
        state = det.update(near)
        assert not state.stop_confirmed

    def test_reset_clears_counter(self, mock_lidar_scan):
        det = FrontWallDetector(stop_distance_m=3.0, confirm_cycles=2)
        scan = mock_lidar_scan(front=2.0)
        det.update(scan)
        det.reset()
        state = det.update(scan)
        assert not state.stop_confirmed

    def test_no_stop_when_far(self, mock_lidar_scan):
        """Front too far -> no stop even after many cycles."""
        det = FrontWallDetector(stop_distance_m=2.0, confirm_cycles=2)
        scan = mock_lidar_scan(front=8.0)
        for _ in range(5):
            state = det.update(scan)
        assert not state.stop_confirmed

    def test_empty_scan_resets_counter(self, mock_lidar_scan):
        """Empty scan handled gracefully -- state says no front wall, counter reset."""
        from scarecrow.sensors.lidar.base import LidarScan
        import numpy as np

        det = FrontWallDetector(stop_distance_m=3.0, confirm_cycles=2)
        near = mock_lidar_scan(front=2.0)
        det.update(near)

        empty = LidarScan(ranges=np.array([]))
        state = det.update(empty)
        assert not state.front_wall_visible
        assert not state.stop_confirmed
