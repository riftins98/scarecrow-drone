"""Safe corner approach controller for lidar-guided starts."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ..sensors.lidar.base import LidarScan
from .wall_follow import VelocityCommand


@dataclass
class CornerApproachResult:
    """Latest command and status from a corner approach update."""

    command: VelocityCommand
    done: bool
    unsafe: bool = False
    reason: str = "approaching"
    rear_distance_m: float | None = None
    side_distance_m: float | None = None


class CornerApproachController:
    """Approach a rear-left or rear-right corner without crossing target bands.

    Unlike ``DistanceStabilizerController``, this controller treats target
    distances as a safe band. It corrects both axes together so lidar feedback
    can counter physical drift, but brakes any axis whose distance is closing
    too quickly near the target band.
    """

    def __init__(
        self,
        *,
        side: str,
        rear_distance: float,
        side_distance: float,
        max_forward_speed: float = 0.18,
        max_lateral_speed: float = 0.18,
        max_total_speed: float = 0.18,
        kp_front_rear: float = 0.35,
        kp_side: float = 0.35,
        tolerance: float = 0.20,
        stable_time: float = 1.0,
        min_clearance: float = 1.0,
        brake_margin: float = 1.0,
        brake_rate_m_s: float = 0.15,
    ):
        if side not in ("left", "right"):
            raise ValueError(f"side must be 'left' or 'right', got {side!r}")
        self.side = side
        self.rear_distance = rear_distance
        self.side_distance = side_distance
        self.max_forward_speed = max_forward_speed
        self.max_lateral_speed = max_lateral_speed
        self.max_total_speed = max_total_speed
        self.kp_front_rear = kp_front_rear
        self.kp_side = kp_side
        self.tolerance = tolerance
        self.stable_time = stable_time
        self.min_clearance = min_clearance
        self.brake_margin = brake_margin
        self.brake_rate_m_s = brake_rate_m_s
        self._stable_since: float | None = None
        self._done = False
        self._prev_rear: float | None = None
        self._prev_side: float | None = None
        self._prev_time: float | None = None

    @property
    def done(self) -> bool:
        return self._done

    def reset(self) -> None:
        self._stable_since = None
        self._done = False
        self._prev_rear = None
        self._prev_side = None
        self._prev_time = None

    def update(self, scan: LidarScan, now: float | None = None) -> CornerApproachResult:
        if self._done:
            return CornerApproachResult(VelocityCommand(), done=True, reason="done")

        now_ts = now if now is not None else time.time()
        rear = scan.rear_distance()
        side_dist = scan.left_distance() if self.side == "left" else scan.right_distance()
        if not math.isfinite(rear) or not math.isfinite(side_dist):
            self._stable_since = None
            return CornerApproachResult(
                VelocityCommand(),
                done=False,
                reason="invalid_scan",
                rear_distance_m=rear,
                side_distance_m=side_dist,
            )

        if rear < self.min_clearance or side_dist < self.min_clearance:
            self._stable_since = None
            self._remember(rear, side_dist, now_ts)
            return CornerApproachResult(
                VelocityCommand(),
                done=False,
                unsafe=True,
                reason="unsafe_clearance",
                rear_distance_m=rear,
                side_distance_m=side_dist,
            )

        rear_error = rear - self.rear_distance
        side_error = side_dist - self.side_distance
        rear_too_far = rear_error > self.tolerance
        side_too_far = side_error > self.tolerance
        rear_too_close = rear_error < -self.tolerance
        side_too_close = side_error < -self.tolerance
        rear_in_zone = not rear_too_far and not rear_too_close
        side_in_zone = not side_too_far and not side_too_close
        rear_rate = self._rate(self._prev_rear, rear, now_ts)
        side_rate = self._rate(self._prev_side, side_dist, now_ts)
        rear_brake = (
            rear <= self.rear_distance + self.brake_margin
            and rear_rate is not None
            and rear_rate < -self.brake_rate_m_s
        )
        side_brake = (
            side_dist <= self.side_distance + self.brake_margin
            and side_rate is not None
            and side_rate < -self.brake_rate_m_s
        )

        if rear_in_zone and side_in_zone and not rear_brake and not side_brake:
            if self._stable_since is None:
                self._stable_since = now_ts
            elif now_ts - self._stable_since >= self.stable_time:
                self._done = True
                self._remember(rear, side_dist, now_ts)
                return CornerApproachResult(
                    VelocityCommand(),
                    done=True,
                    reason="reached",
                    rear_distance_m=rear,
                    side_distance_m=side_dist,
                )
            self._remember(rear, side_dist, now_ts)
            return CornerApproachResult(
                VelocityCommand(),
                done=False,
                reason="settling",
                rear_distance_m=rear,
                side_distance_m=side_dist,
            )

        self._stable_since = None
        if rear_too_close or rear_brake:
            forward = -self.kp_front_rear * rear_error
            if rear_brake and forward <= 0.0:
                forward = self.max_forward_speed
            forward = max(0.0, min(self.max_forward_speed, forward))
        elif rear_too_far:
            forward = -self.kp_front_rear * rear_error
            forward = max(-self.max_forward_speed, min(0.0, forward))
        else:
            forward = 0.0

        if side_too_close or side_brake:
            lateral = -self.kp_side * side_error
            if side_brake and lateral <= 0.0:
                lateral = self.max_lateral_speed
            lateral = max(0.0, min(self.max_lateral_speed, lateral))
            right = lateral if self.side == "left" else -lateral
        elif side_too_far:
            lateral = self.kp_side * side_error
            lateral = max(0.0, min(self.max_lateral_speed, lateral))
            right = -lateral if self.side == "left" else lateral
        else:
            right = 0.0

        speed = math.hypot(forward, right)
        if speed > self.max_total_speed > 0.0:
            scale = self.max_total_speed / speed
            forward *= scale
            right *= scale

        self._remember(rear, side_dist, now_ts)
        return CornerApproachResult(
            VelocityCommand(forward_m_s=forward, right_m_s=right),
            done=False,
            reason="approaching",
            rear_distance_m=rear,
            side_distance_m=side_dist,
        )

    def _rate(self, previous: float | None, current: float, now_ts: float) -> float | None:
        if previous is None or self._prev_time is None:
            return None
        dt = now_ts - self._prev_time
        if dt <= 0.0:
            return None
        return (current - previous) / dt

    def _remember(self, rear: float, side_dist: float, now_ts: float) -> None:
        self._prev_rear = rear
        self._prev_side = side_dist
        self._prev_time = now_ts
