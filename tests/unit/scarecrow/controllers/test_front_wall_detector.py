"""UT-06..07: FrontWallDetector tests (ADD Section 5.4).

NOTE: confirmation is a DURATION, not a call count. It used to be
`confirm_cycles` consecutive update() calls, which tied it to the caller's loop
rate -- raising the wall-follow rate from 7Hz to 12.8Hz halved the real
confirmation window and the detector confirmed a wall that was not there. The
`confirm_cycles` argument is still accepted and converted to seconds at the
7Hz it was tuned against; these tests now advance real time.
"""
import time

from scarecrow.controllers.front_wall_detector import FrontWallDetector


class TestFrontWallDetector:
    def test_no_stop_on_first_cycle(self, mock_lidar_scan):
        """UT-06: Requires confirm_cycles consecutive detections before stopping."""
        det = FrontWallDetector(stop_distance_m=3.0, confirm_cycles=3)
        scan = mock_lidar_scan(front=2.0)
        state = det.update(scan)
        assert not state.stop_confirmed

    def test_confirms_after_the_window_elapses(self, mock_lidar_scan):
        """UT-07: Stop confirmed once the detection has PERSISTED long enough.

        Two back-to-back calls no longer confirm, however many there are --
        that was the rate-dependent bug. The evidence has to last.
        """
        det = FrontWallDetector(stop_distance_m=3.0, confirm_seconds=0.10)
        scan = mock_lidar_scan(front=2.0)

        det.update(scan)
        assert not det.update(scan).stop_confirmed, "confirmed on call count"

        time.sleep(0.12)
        assert det.update(scan).stop_confirmed

    def test_window_restarts_on_clear(self, mock_lidar_scan):
        """If the front clears, the window restarts -- evidence must be continuous."""
        det = FrontWallDetector(stop_distance_m=3.0, confirm_seconds=0.10)
        near = mock_lidar_scan(front=2.0)
        far = mock_lidar_scan(front=8.0)

        det.update(near)
        time.sleep(0.08)
        det.update(far)          # cleared -- restart
        time.sleep(0.08)

        assert not det.update(near).stop_confirmed

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
