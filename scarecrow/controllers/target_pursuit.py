"""Target pursuit controller using vision alignment and lidar range."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum

from ..sensors.lidar.base import LidarScan
from .wall_follow import VelocityCommand


class TargetPursuitState(str, Enum):
    """High-level target pursuit phases."""

    ALIGNING = "ALIGNING"
    APPROACHING = "APPROACHING"
    SEARCHING = "SEARCHING"
    TARGET_REACHED = "TARGET_REACHED"
    WALL_SAFETY = "WALL_SAFETY"
    LOST = "LOST"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True)
class TargetObservation:
    """Latest target position in image coordinates."""

    center_x: float
    center_y: float
    image_width: float
    confidence: float
    timestamp: float
    class_name: str | None = None
    bbox: tuple[int, int, int, int] | None = None

    def age(self, now: float | None = None) -> float:
        return (time.time() if now is None else now) - self.timestamp


@dataclass
class TargetPursuitConfig:
    """Configuration for lidar-and-vision target pursuit."""

    target_distance_m: float = 1.5
    max_forward_speed_m_s: float = 0.4
    min_forward_speed_m_s: float = 0.05
    kp_forward: float = 0.3
    yaw_kp: float = 15.0
    max_yaw_speed_deg_s: float = 20.0
    min_wall_distance_m: float = 0.8
    side_wall_push_m_s: float = 0.15
    center_enter_ratio: float = 0.05
    center_exit_ratio: float = 0.08
    detection_miss_timeout_s: float = 1.8
    detection_miss_count_required: int = 2
    pursuit_timeout_s: float = 45.0
    search_right_deg: float = 25.0
    search_left_deg: float = 50.0
    search_yaw_speed_deg_s: float = 25.0


@dataclass(frozen=True)
class TargetPursuitResult:
    """Result of one target pursuit controller update."""

    state: TargetPursuitState
    command: VelocityCommand
    done: bool = False
    reached_target: bool = False
    reason: str = ""
    front_distance_m: float | None = None
    target_age_s: float | None = None
    center_error_ratio: float | None = None
    elapsed_s: float = 0.0


class TargetPursuitController:
    """Pure controller for target pursuit.

    The controller does no IO. It consumes a lidar scan and the latest target
    observation, then returns a body-frame velocity command and state summary.
    Async loops, search rotations, telemetry, and logging belong to callers.
    """

    def __init__(self, config: TargetPursuitConfig | None = None) -> None:
        self.config = config or TargetPursuitConfig()
        self.state = TargetPursuitState.ALIGNING
        self._start_time: float | None = None
        self._miss_count = 0

    def reset(self) -> None:
        self.state = TargetPursuitState.ALIGNING
        self._start_time = None
        self._miss_count = 0

    def update(
        self,
        scan: LidarScan,
        observation: TargetObservation | None,
        now: float | None = None,
    ) -> TargetPursuitResult:
        """Return the next velocity command for the current scan/observation."""
        now_ts = time.time() if now is None else now
        if self._start_time is None:
            self._start_time = now_ts
        elapsed = now_ts - self._start_time

        if elapsed >= self.config.pursuit_timeout_s:
            self.state = TargetPursuitState.TIMEOUT
            return self._result(done=True, reason="timeout", elapsed=elapsed)

        front_dist = scan.front_distance()
        left_dist = scan.left_distance()
        right_dist = scan.right_distance()

        if min(left_dist, right_dist) < self.config.min_wall_distance_m:
            self.state = TargetPursuitState.WALL_SAFETY
            return self._result(
                done=True,
                reason="wall_safety",
                front_distance=front_dist,
                elapsed=elapsed,
            )

        if front_dist <= self.config.target_distance_m:
            self.state = TargetPursuitState.TARGET_REACHED
            return self._result(
                done=True,
                reached_target=True,
                reason="target_reached",
                front_distance=front_dist,
                elapsed=elapsed,
            )

        target_age = observation.age(now_ts) if observation is not None else math.inf
        if target_age > self.config.detection_miss_timeout_s:
            self._miss_count += 1
        else:
            self._miss_count = 0

        if self._miss_count >= self.config.detection_miss_count_required:
            self.state = TargetPursuitState.SEARCHING
            return self._result(
                reason="target_missing",
                front_distance=front_dist,
                target_age=target_age,
                elapsed=elapsed,
            )

        centered = self._is_centered(observation)
        center_error = self._center_error_ratio(observation)
        yaw = self._align_yaw(observation)
        if not centered:
            self.state = TargetPursuitState.ALIGNING
            return self._result(
                command=VelocityCommand(yawspeed_deg_s=yaw),
                reason="aligning",
                front_distance=front_dist,
                target_age=target_age,
                center_error=center_error,
                elapsed=elapsed,
            )

        self.state = TargetPursuitState.APPROACHING
        base_cmd = self._approach_command(front_dist, left_dist, right_dist)
        return self._result(
            command=VelocityCommand(
                forward_m_s=base_cmd.forward_m_s,
                right_m_s=base_cmd.right_m_s,
                down_m_s=0.0,
                yawspeed_deg_s=yaw,
            ),
            reason="approaching",
            front_distance=front_dist,
            target_age=target_age,
            center_error=center_error,
            elapsed=elapsed,
        )

    def mark_reacquired(self) -> None:
        """Reset miss accounting after an external search finds the target."""
        self._miss_count = 0
        self.state = TargetPursuitState.ALIGNING

    def _approach_command(
        self,
        front_dist: float,
        left_dist: float,
        right_dist: float,
    ) -> VelocityCommand:
        dist_error = front_dist - self.config.target_distance_m
        if dist_error <= 0:
            forward = 0.0
        else:
            forward = min(
                self.config.kp_forward * dist_error,
                self.config.max_forward_speed_m_s,
            )
            forward = max(forward, self.config.min_forward_speed_m_s)

        right = 0.0
        if left_dist < self.config.min_wall_distance_m:
            right = self.config.side_wall_push_m_s
        elif right_dist < self.config.min_wall_distance_m:
            right = -self.config.side_wall_push_m_s

        return VelocityCommand(forward_m_s=forward, right_m_s=right)

    def _is_centered(self, observation: TargetObservation | None) -> bool:
        if observation is None:
            return False
        ratio = (
            self.config.center_exit_ratio
            if self.state == TargetPursuitState.APPROACHING
            else self.config.center_enter_ratio
        )
        image_cx = observation.image_width / 2.0
        return abs(observation.center_x - image_cx) <= image_cx * ratio

    def _center_error_ratio(
        self,
        observation: TargetObservation | None,
    ) -> float | None:
        if observation is None:
            return None
        image_cx = observation.image_width / 2.0
        return abs(observation.center_x - image_cx) / image_cx

    def _align_yaw(self, observation: TargetObservation | None) -> float:
        if observation is None:
            return 0.0
        image_cx = observation.image_width / 2.0
        yaw_error = (observation.center_x - image_cx) / image_cx
        yaw = yaw_error * self.config.yaw_kp
        return max(-self.config.max_yaw_speed_deg_s, min(self.config.max_yaw_speed_deg_s, yaw))

    def _result(
        self,
        command: VelocityCommand | None = None,
        *,
        done: bool = False,
        reached_target: bool = False,
        reason: str = "",
        front_distance: float | None = None,
        target_age: float | None = None,
        center_error: float | None = None,
        elapsed: float = 0.0,
    ) -> TargetPursuitResult:
        return TargetPursuitResult(
            state=self.state,
            command=command or VelocityCommand(),
            done=done,
            reached_target=reached_target,
            reason=reason,
            front_distance_m=front_distance,
            target_age_s=target_age,
            center_error_ratio=center_error,
            elapsed_s=elapsed,
        )
