"""Distance-based point stabilizer for lidar-guided positioning.

This controller drives the drone in body frame to satisfy optional
front/rear/left/right distance constraints simultaneously.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..sensors.lidar.base import LidarScan
from .wall_follow import VelocityCommand


@dataclass
class DistanceTargets:
    """Optional distance targets in meters.

    Any field set to None is ignored.
    """

    front: float | None = None
    rear: float | None = None
    left: float | None = None
    right: float | None = None


class DistanceStabilizerController:
    """Stabilize at a point defined by wall-distance constraints.

    Examples:
      - front=3, left=1
      - rear=2, right=4
      - front=3, rear=2, left=1, right=4

    The controller outputs body-frame velocity commands and reports done=True
    only after all requested constraints stay within tolerance for stable_time.
    """

    def __init__(
        self,
        targets: DistanceTargets,
        kp_front_rear: float = 0.40,
        kp_left_right: float = 0.45,
        max_forward_speed: float = 0.25,
        max_lateral_speed: float = 0.25,
        tolerance: float = 0.15,
        stable_time: float = 1.0,
    ):
        if all(
            t is None
            for t in (targets.front, targets.rear, targets.left, targets.right)
        ):
            raise ValueError("At least one target must be provided")

        self.targets = targets
        self.kp_front_rear = kp_front_rear
        self.kp_left_right = kp_left_right
        self.max_forward_speed = max_forward_speed
        self.max_lateral_speed = max_lateral_speed
        self.tolerance = tolerance
        self.stable_time = stable_time

        self._stable_since: float | None = None
        self._done = False

    @property
    def done(self) -> bool:
        return self._done

    def reset(self) -> None:
        self._stable_since = None
        self._done = False

    def update(self, scan: LidarScan, now: float | None = None) -> VelocityCommand:
        """Compute a body-frame velocity command from latest lidar scan."""
        if self._done:
            return VelocityCommand()

        now_ts = now if now is not None else time.time()

        distances = {
            "front": scan.front_distance(),
            "rear": scan.rear_distance(),
            "left": scan.left_distance(),
            "right": scan.right_distance(),
        }

        errors: dict[str, float] = {}
        for key, target in (
            ("front", self.targets.front),
            ("rear", self.targets.rear),
            ("left", self.targets.left),
            ("right", self.targets.right),
        ):
            if target is None:
                continue
            value = distances[key]
            if not math.isfinite(value):
                self._stable_since = None
                return VelocityCommand()
            errors[key] = value - target

        # Body X (forward):
        #  - front error positive => move forward (+)
        #  - rear error positive => move backward (-)
        forward = 0.0
        if "front" in errors:
            forward += self.kp_front_rear * errors["front"]
        if "rear" in errors:
            forward -= self.kp_front_rear * errors["rear"]

        # Body Y (right):
        #  - left error positive => move left (-right)
        #  - right error positive => move right (+right)
        right = 0.0
        if "left" in errors:
            right -= self.kp_left_right * errors["left"]
        if "right" in errors:
            right += self.kp_left_right * errors["right"]

        forward = max(-self.max_forward_speed, min(self.max_forward_speed, forward))
        right = max(-self.max_lateral_speed, min(self.max_lateral_speed, right))

        within_tolerance = all(abs(err) <= self.tolerance for err in errors.values())
        if within_tolerance:
            if self._stable_since is None:
                self._stable_since = now_ts
            elif now_ts - self._stable_since >= self.stable_time:
                self._done = True
                return VelocityCommand()
        else:
            self._stable_since = None

        return VelocityCommand(forward_m_s=forward, right_m_s=right)
