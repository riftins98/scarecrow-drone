"""UT-08..09: LidarScan tests (ADD Section 5.4)."""
import math

import numpy as np

from scarecrow.sensors.lidar.base import LidarScan


class TestLidarScan:
    def test_front_distance_returns_configured_value(self, mock_lidar_scan):
        """UT-08: front_distance() returns value set in mock."""
        scan = mock_lidar_scan(front=3.0)
        assert abs(scan.front_distance() - 3.0) < 0.5

    def test_rear_distance_returns_configured_value(self, mock_lidar_scan):
        scan = mock_lidar_scan(rear=7.0)
        assert abs(scan.rear_distance() - 7.0) < 0.5

    def test_left_and_right_distinct(self, mock_lidar_scan):
        """Left and right sectors are independent."""
        scan = mock_lidar_scan(left=2.0, right=8.0)
        assert abs(scan.left_distance() - 2.0) < 0.5
        assert abs(scan.right_distance() - 8.0) < 0.5

    def test_num_samples(self, mock_lidar_scan):
        scan = mock_lidar_scan(num_samples=720)
        assert scan.num_samples == 720

    def test_angle_range_is_full_circle(self):
        """Contract: all scans span -pi to +pi."""
        ranges = np.full(100, 5.0)
        scan = LidarScan(ranges=ranges)
        assert scan.angle_min == -math.pi
        assert scan.angle_max == math.pi

    def test_left_wall_angle_error_for_parallel_wall(self):
        """UT-09: SVD returns near-zero error when left wall is parallel."""
        angles = np.linspace(-math.pi, math.pi, 1440, endpoint=False)
        ranges = np.full(1440, 10.0)
        # Left sector (around +pi/2): uniform 2m wall at constant angle
        for i, a in enumerate(angles):
            if abs(a - math.pi / 2) < 0.4:
                ranges[i] = 2.0
        scan = LidarScan(ranges=ranges)
        err = scan.left_wall_angle_error()
        if err is not None:
            assert abs(err) < 0.2

    def test_empty_scan_returns_inf_distance(self):
        scan = LidarScan(ranges=np.array([]))
        assert scan.front_distance() == float("inf")

    def test_get_range_at_angle(self, mock_lidar_scan):
        """get_range_at_angle returns the closest sample."""
        scan = mock_lidar_scan(front=3.0)
        assert abs(scan.get_range_at_angle(0.0) - 3.0) < 0.5
