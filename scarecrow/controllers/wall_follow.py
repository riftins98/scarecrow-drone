"""Wall-following controller using 2D lidar."""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class VelocityCommand:
    """Body-frame velocity command for the drone.

    Attributes:
        forward_m_s: Forward speed (positive = nose direction).
        right_m_s: Lateral speed (positive = right).
        down_m_s: Vertical speed (positive = descend). 0 = hold altitude.
        yawspeed_deg_s: Yaw rate in deg/s. 0 = hold heading.
    """
    forward_m_s: float = 0.0
    right_m_s: float = 0.0
    down_m_s: float = 0.0
    yawspeed_deg_s: float = 0.0

    @property
    def is_zero(self) -> bool:
        return (abs(self.forward_m_s) < 0.01
                and abs(self.right_m_s) < 0.01
                and abs(self.down_m_s) < 0.01
                and abs(self.yawspeed_deg_s) < 0.1)


class WallFollowController:
    """PD controller for wall following using lidar.

    Flies forward at a constant speed while maintaining a target distance
    from a wall (left or right). Stops when the front wall is within a threshold.

    Args:
        side: Which wall to follow — "left" or "right".
        target_distance: Desired distance from the wall (meters).
        forward_speed: Cruise speed along the wall (m/s).
        front_stop_distance: Stop when front wall closer than this (meters).
        kp: Proportional gain for lateral correction.
        kd: Derivative gain for lateral correction.
        max_lateral_speed: Clamp lateral corrections (m/s).
        min_safe_distance: Emergency stop if any wall closer than this (meters).
        yaw_kp: Proportional gain for yaw correction (SVD wall alignment).
        max_yaw_speed: Max yaw correction speed (deg/s).
    """

    def __init__(
        self,
        side: str = "left",
        target_distance: float = 2.0,
        forward_speed: float = 0.3,
        front_stop_distance: float = 2.0,
        kp: float = 0.4,
        kd: float = 0.1,
        max_lateral_speed: float = 0.3,
        min_safe_distance: float = 0.5,
        yaw_kp: float = 1.5,
        max_yaw_speed: float = 10.0,
    ):
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got '{side}'")
        self.side = side
        self.target_distance = target_distance
        self.forward_speed = forward_speed
        self.front_stop_distance = front_stop_distance
        self.kp = kp
        self.kd = kd
        self.max_lateral_speed = max_lateral_speed
        self.min_safe_distance = min_safe_distance
        self.yaw_kp = yaw_kp
        self.max_yaw_speed = max_yaw_speed
        self._prev_error: float | None = None
        self._reached_front_wall = False
        # Sign: left wall → negative lateral pushes left (toward wall)
        #        right wall → positive lateral pushes right (toward wall)
        self._lateral_sign = -1 if side == "left" else 1

    @property
    def done(self) -> bool:
        """True when the drone has reached the front wall stop distance."""
        return self._reached_front_wall

    def reset(self) -> None:
        """Reset controller state for a new run."""
        self._prev_error = None
        self._reached_front_wall = False

    def update(self, wall_dist: float, front_dist: float,
               wall_angle_error: float | None = None,
               front_wall_confirmed: bool = True,
               front_stop_reached: bool = False) -> VelocityCommand:
        """Compute velocity command from lidar distances and wall alignment.

        Args:
            wall_dist: Distance to the followed wall (left or right, meters).
            front_dist: Distance to the front wall (meters).
            wall_angle_error: Signed angle error from being parallel to the
                followed wall (radians). 0 = parallel. None = skip yaw correction.
            front_wall_confirmed: If False, ignore front stop threshold for this
                cycle (useful when nearest front return is likely not the wall).
            front_stop_reached: External stop confirmation from perception layer.

        Returns:
            VelocityCommand for the drone.
        """
        # Emergency stop: too close to any wall
        if wall_dist < self.min_safe_distance or front_dist < self.min_safe_distance:
            self._reached_front_wall = True
            return VelocityCommand()

        # Reached front wall → stop
        if front_dist <= self.front_stop_distance and front_wall_confirmed:
            self._reached_front_wall = True
            return VelocityCommand()

        if front_stop_reached:
            self._reached_front_wall = True
            return VelocityCommand()

        # PD control for lateral distance to wall
        error = wall_dist - self.target_distance  # positive = too far from wall

        d_error = 0.0
        if self._prev_error is not None:
            d_error = error - self._prev_error
        self._prev_error = error

        # Lateral correction toward/away from wall
        lateral = self._lateral_sign * (self.kp * error + self.kd * d_error)
        lateral = max(-self.max_lateral_speed, min(self.max_lateral_speed, lateral))

        # Yaw correction: keep drone parallel to wall using lidar SVD
        yaw = 0.0
        if wall_angle_error is not None:
            yaw_deg = math.degrees(wall_angle_error)
            yaw = -yaw_deg * self.yaw_kp
            yaw = max(-self.max_yaw_speed, min(self.max_yaw_speed, yaw))

        return VelocityCommand(
            forward_m_s=self.forward_speed,
            right_m_s=lateral,
            down_m_s=0.0,
            yawspeed_deg_s=yaw,
        )
