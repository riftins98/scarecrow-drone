"""UT-01..03: WallFollowController tests (ADD Section 5.4)."""
from scarecrow.controllers.wall_follow import WallFollowController


class TestWallFollowController:
    def test_pushes_toward_wall_when_too_far(self):
        """UT-01: Left wall, drone too far -> negative right_m_s (push left)."""
        ctrl = WallFollowController(side="left", target_distance=2.0)
        cmd = ctrl.update(wall_dist=3.0, front_dist=10.0)
        assert cmd.right_m_s < 0
        assert cmd.forward_m_s > 0

    def test_pushes_away_from_wall_when_too_close(self):
        """UT-01: Left wall, drone too close -> positive right_m_s (push right)."""
        ctrl = WallFollowController(side="left", target_distance=2.0)
        cmd = ctrl.update(wall_dist=1.0, front_dist=10.0)
        assert cmd.right_m_s > 0

    def test_emergency_stop_when_wall_too_close(self):
        """UT-02: Emergency stop when any wall closer than min_safe_distance."""
        ctrl = WallFollowController(side="left", min_safe_distance=0.5)
        cmd = ctrl.update(wall_dist=0.3, front_dist=10.0)
        assert cmd.is_zero
        assert ctrl.done

    def test_stops_at_front_wall(self):
        """UT-03: Stops when front wall within stop distance."""
        ctrl = WallFollowController(side="left", front_stop_distance=2.0)
        cmd = ctrl.update(wall_dist=2.0, front_dist=1.5)
        assert cmd.is_zero
        assert ctrl.done

    def test_front_stop_requires_confirmation(self):
        """front_wall_confirmed=False skips front-wall stop."""
        ctrl = WallFollowController(side="left", front_stop_distance=2.0)
        cmd = ctrl.update(wall_dist=2.0, front_dist=1.5, front_wall_confirmed=False)
        assert not ctrl.done

    def test_reset_clears_done(self):
        ctrl = WallFollowController(side="left", front_stop_distance=2.0)
        ctrl.update(wall_dist=2.0, front_dist=1.0)
        assert ctrl.done
        ctrl.reset()
        assert not ctrl.done

    def test_yaw_correction_applied_when_angle_error_given(self):
        ctrl = WallFollowController(side="left")
        cmd_no_error = ctrl.update(wall_dist=2.0, front_dist=10.0)
        ctrl2 = WallFollowController(side="left")
        cmd_with_error = ctrl2.update(wall_dist=2.0, front_dist=10.0, wall_angle_error=0.1)
        assert cmd_no_error.yawspeed_deg_s == 0
        assert cmd_with_error.yawspeed_deg_s != 0

    def test_invalid_side_raises(self):
        import pytest
        with pytest.raises(ValueError):
            WallFollowController(side="back")

    def test_right_wall_mirror_signs(self):
        """Right-wall controller uses opposite lateral sign from left."""
        left = WallFollowController(side="left", target_distance=2.0)
        right = WallFollowController(side="right", target_distance=2.0)
        left_cmd = left.update(wall_dist=3.0, front_dist=10.0)
        right_cmd = right.update(wall_dist=3.0, front_dist=10.0)
        assert (left_cmd.right_m_s < 0) != (right_cmd.right_m_s < 0)
