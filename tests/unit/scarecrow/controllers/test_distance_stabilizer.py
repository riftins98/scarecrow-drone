"""UT-04..05: DistanceStabilizerController tests (ADD Section 5.4)."""
import pytest

from scarecrow.controllers.distance_stabilizer import (
    DistanceStabilizerController,
    DistanceTargets,
)


class TestDistanceStabilizer:
    def test_requires_at_least_one_target(self):
        with pytest.raises(ValueError):
            DistanceStabilizerController(targets=DistanceTargets())

    def test_converges_toward_front_target(self, mock_lidar_scan):
        """UT-04: front too far -> forward velocity positive."""
        targets = DistanceTargets(front=3.0)
        ctrl = DistanceStabilizerController(targets=targets)
        scan = mock_lidar_scan(front=5.0)
        cmd = ctrl.update(scan)
        assert cmd.forward_m_s > 0

    def test_converges_toward_rear_target(self, mock_lidar_scan):
        """rear too far -> forward velocity negative (backward)."""
        targets = DistanceTargets(rear=3.0)
        ctrl = DistanceStabilizerController(targets=targets)
        scan = mock_lidar_scan(rear=5.0)
        cmd = ctrl.update(scan)
        assert cmd.forward_m_s < 0

    def test_converges_toward_left_target(self, mock_lidar_scan):
        """left too far -> negative right_m_s (move left)."""
        targets = DistanceTargets(left=2.0)
        ctrl = DistanceStabilizerController(targets=targets)
        scan = mock_lidar_scan(left=4.0)
        cmd = ctrl.update(scan)
        assert cmd.right_m_s < 0

    def test_done_when_within_tolerance(self, mock_lidar_scan):
        """UT-05: Reports done when all targets within tolerance for stable_time."""
        targets = DistanceTargets(front=5.0, left=2.0)
        ctrl = DistanceStabilizerController(
            targets=targets, tolerance=0.5, stable_time=0.0
        )
        scan = mock_lidar_scan(front=5.1, left=2.1)
        ctrl.update(scan, now=0.0)
        ctrl.update(scan, now=0.1)
        assert ctrl.done

    def test_stability_resets_on_error(self, mock_lidar_scan):
        """Out-of-tolerance readings reset the stable timer."""
        targets = DistanceTargets(front=5.0)
        ctrl = DistanceStabilizerController(
            targets=targets, tolerance=0.2, stable_time=1.0
        )
        good = mock_lidar_scan(front=5.0)
        bad = mock_lidar_scan(front=8.0)
        ctrl.update(good, now=0.0)
        ctrl.update(good, now=0.5)
        ctrl.update(bad, now=1.0)
        assert not ctrl.done

    def test_reset_clears_done(self, mock_lidar_scan):
        targets = DistanceTargets(front=5.0)
        ctrl = DistanceStabilizerController(
            targets=targets, tolerance=0.5, stable_time=0.0
        )
        scan = mock_lidar_scan(front=5.0)
        ctrl.update(scan, now=0.0)
        ctrl.update(scan, now=0.1)
        assert ctrl.done
        ctrl.reset()
        assert not ctrl.done

    def test_velocity_clamped_to_max(self, mock_lidar_scan):
        """Large errors don't produce velocities above max_forward_speed."""
        targets = DistanceTargets(front=3.0)
        ctrl = DistanceStabilizerController(
            targets=targets, max_forward_speed=0.25
        )
        scan = mock_lidar_scan(front=20.0)  # huge error
        cmd = ctrl.update(scan)
        assert abs(cmd.forward_m_s) <= 0.25
