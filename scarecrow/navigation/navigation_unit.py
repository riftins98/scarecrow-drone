"""Unified navigation interface combining wall-follow, stabilize, and rotate.

Thin facade over the existing controllers in `scarecrow.controllers`. The
controllers themselves remain the source of truth for PD math and state
machines -- this class just wires them to a Drone + LidarSource and runs
the async offboard loop.

Usage:
    nav = NavigationUnit(drone, lidar)
    await nav.wall_follow(side="left", target_distance=2.0)
    await nav.rotate(direction="right")
    await nav.stabilize(DistanceTargets(front=3.0, left=2.0))
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Callable

from ..controllers.distance_stabilizer import DistanceTargets
from ..controllers.front_wall_detector import FrontWallDetector
from ..controllers.rotation import rotate_90
from ..controllers.target_pursuit import (
    TargetPursuitConfig,
    TargetPursuitController,
    TargetPursuitResult,
    TargetPursuitState,
)
from ..controllers.wall_follow import VelocityCommand, WallFollowController
from ..drone import Drone
from ..flight.stabilization import lidar_stabilize
from ..sensors.lidar.base import LidarSource


@dataclass(frozen=True)
class WallFollowResult:
    """Result for a wall-follow segment."""

    done: bool
    reason: str
    elapsed_s: float = 0.0
    front_distance_m: float | None = None
    wall_distance_m: float | None = None
    raw_front_distance_m: float | None = None
    center_front_distance_m: float | None = None
    front_wall_visible: bool = False
    stop_confirmed: bool = False
    command: VelocityCommand | None = None


@dataclass(frozen=True)
class CeilingClearanceResult:
    """Result for a ceiling-clearance safety check."""

    done: bool
    reason: str
    clearance_m: float | None = None
    elapsed_s: float = 0.0


class NavigationUnit:
    """Combines the flight controllers into a single navigation API.

    Args:
        drone: Connected Drone instance (must already be in offboard mode).
        lidar: Active LidarSource providing scans.
    """

    def __init__(self, drone: Drone, lidar: LidarSource):
        self.drone = drone
        self.lidar = lidar

    async def wall_follow(
        self,
        side: str = "left",
        target_distance: float = 2.0,
        forward_speed: float = 0.3,
        front_stop_distance: float = 2.0,
        timeout: float = 30.0,
        kp: float = 0.4,
        kd: float = 0.1,
        max_lateral_speed: float = 0.3,
        min_safe_distance: float = 0.5,
        yaw_kp: float = 1.5,
        max_yaw_speed: float = 10.0,
    ) -> bool:
        """Follow a wall until front obstacle detected. Returns True if stopped
        normally, False on timeout."""
        result = await self.wall_follow_until(
            side=side,
            target_distance=target_distance,
            forward_speed=forward_speed,
            front_stop_distance=front_stop_distance,
            timeout=timeout,
            kp=kp,
            kd=kd,
            max_lateral_speed=max_lateral_speed,
            min_safe_distance=min_safe_distance,
            yaw_kp=yaw_kp,
            max_yaw_speed=max_yaw_speed,
        )
        return result.done and result.reason == "front_wall"

    async def wall_follow_until(
        self,
        side: str = "left",
        target_distance: float = 2.0,
        forward_speed: float = 0.3,
        front_stop_distance: float = 2.0,
        timeout: float = 30.0,
        stop_condition: Callable[[], bool] | None = None,
        on_status: Callable[[WallFollowResult], None] | None = None,
        kp: float = 0.4,
        kd: float = 0.1,
        max_lateral_speed: float = 0.3,
        min_safe_distance: float = 0.5,
        yaw_kp: float = 1.5,
        max_yaw_speed: float = 10.0,
    ) -> WallFollowResult:
        """Follow a wall until a front wall, timeout, or external condition.

        Args:
            side: Which wall to follow, ``"left"`` or ``"right"``.
            target_distance: Desired distance from followed wall in meters.
            forward_speed: Cruise speed in meters per second.
            front_stop_distance: Stop when front wall is confirmed this close.
            timeout: Maximum segment duration in seconds.
            stop_condition: Optional synchronous predicate checked each loop.
            on_status: Optional callback with the latest segment status.
        """
        ctrl = WallFollowController(
            side=side,
            target_distance=target_distance,
            forward_speed=forward_speed,
            front_stop_distance=front_stop_distance,
            kp=kp,
            kd=kd,
            max_lateral_speed=max_lateral_speed,
            min_safe_distance=min_safe_distance,
            yaw_kp=yaw_kp,
            max_yaw_speed=max_yaw_speed,
        )
        front_detector = FrontWallDetector(
            stop_distance_m=front_stop_distance,
        )

        loop = asyncio.get_event_loop()
        started_at = loop.time()
        deadline = started_at + timeout
        last_status = WallFollowResult(False, "timeout", elapsed_s=0.0)
        while loop.time() < deadline:
            elapsed = loop.time() - started_at
            if stop_condition is not None and stop_condition():
                await self.drone.set_velocity(VelocityCommand())
                return WallFollowResult(
                    True,
                    "interrupted",
                    elapsed_s=elapsed,
                    front_distance_m=last_status.front_distance_m,
                    wall_distance_m=last_status.wall_distance_m,
                    raw_front_distance_m=last_status.raw_front_distance_m,
                    center_front_distance_m=last_status.center_front_distance_m,
                    front_wall_visible=last_status.front_wall_visible,
                    stop_confirmed=last_status.stop_confirmed,
                    command=last_status.command,
                )

            scan = self.lidar.get_scan()
            if scan is None:
                await self.drone.set_velocity(VelocityCommand())
                await asyncio.sleep(0.05)
                continue

            wall_dist = (
                scan.left_distance() if side == "left" else scan.right_distance()
            )
            wall_error = (
                scan.left_wall_angle_error()
                if side == "left"
                else scan.right_wall_angle_error()
            )
            front_state = front_detector.update(scan)

            cmd = ctrl.update(
                wall_dist=wall_dist,
                front_dist=front_state.robust_front_m,
                wall_angle_error=wall_error,
                front_wall_confirmed=front_state.front_wall_visible,
                front_stop_reached=front_state.stop_confirmed,
            )
            await self.drone.set_velocity(cmd)

            status = WallFollowResult(
                done=ctrl.done,
                reason="front_wall" if ctrl.done else "following",
                elapsed_s=elapsed,
                front_distance_m=front_state.robust_front_m,
                wall_distance_m=wall_dist,
                raw_front_distance_m=front_state.raw_front_min_m,
                center_front_distance_m=front_state.center_front_m,
                front_wall_visible=front_state.front_wall_visible,
                stop_confirmed=front_state.stop_confirmed,
                command=cmd,
            )
            last_status = status
            if on_status is not None:
                on_status(status)

            if ctrl.done:
                await self.drone.set_velocity(VelocityCommand())
                reason = "wall_safety"
                if front_state.stop_confirmed or (
                    front_state.front_wall_visible
                    and front_state.robust_front_m <= front_stop_distance
                ):
                    reason = "front_wall"
                return WallFollowResult(
                    True,
                    reason,
                    elapsed_s=elapsed,
                    front_distance_m=front_state.robust_front_m,
                    wall_distance_m=wall_dist,
                    raw_front_distance_m=front_state.raw_front_min_m,
                    center_front_distance_m=front_state.center_front_m,
                    front_wall_visible=front_state.front_wall_visible,
                    stop_confirmed=front_state.stop_confirmed,
                    command=cmd,
                )
            await asyncio.sleep(0.05)

        await self.drone.set_velocity(VelocityCommand())
        return WallFollowResult(
            False,
            "timeout",
            elapsed_s=timeout,
            front_distance_m=last_status.front_distance_m,
            wall_distance_m=last_status.wall_distance_m,
            raw_front_distance_m=last_status.raw_front_distance_m,
            center_front_distance_m=last_status.center_front_distance_m,
            front_wall_visible=last_status.front_wall_visible,
            stop_confirmed=last_status.stop_confirmed,
            command=last_status.command,
        )

    async def hover(self, duration_s: float) -> None:
        """Hold position by sending zero body-frame velocity for a duration."""
        deadline = asyncio.get_event_loop().time() + max(0.0, duration_s)
        while asyncio.get_event_loop().time() < deadline:
            await self.drone.set_velocity(VelocityCommand())
            await asyncio.sleep(0.05)
        await self.drone.set_velocity(VelocityCommand())

    def check_ceiling_clearance(
        self,
        ceiling_sensor,
        min_clearance_m: float,
    ) -> CeilingClearanceResult:
        """Check upward rangefinder clearance without changing altitude.

        Returns ``done=False`` when the reading is missing or below the minimum
        safe clearance so callers can abort the current mission phase.
        """
        clearance = ceiling_sensor.get_distance_m()
        if clearance is None:
            return CeilingClearanceResult(False, "no_data", clearance_m=None)
        if clearance < min_clearance_m:
            return CeilingClearanceResult(
                False,
                "ceiling_safety",
                clearance_m=clearance,
            )
        return CeilingClearanceResult(True, "safe", clearance_m=clearance)

    async def stabilize(
        self,
        targets: DistanceTargets,
        label: str = "stabilize",
        timeout: float = 12.0,
    ) -> bool:
        """Hold position at specified wall distances. Delegates to existing
        `lidar_stabilize` helper."""
        return await lidar_stabilize(
            self.drone.system,
            self.lidar,
            targets,
            label=label,
            timeout=timeout,
        )

    async def rotate(self, direction: str = "right") -> bool:
        """Rotate 90 degrees using compass + lidar SVD. Delegates to existing
        `rotate_90` helper."""
        return await rotate_90(self.drone.system, self.lidar, direction=direction)

    async def pursue_target(
        self,
        tracker,
        config: TargetPursuitConfig | None = None,
        on_status: Callable[[TargetPursuitResult], None] | None = None,
    ) -> TargetPursuitResult:
        """Pursue the latest tracked target using lidar range and camera centering.

        Args:
            tracker: Object exposing ``latest(max_age_s=None, now=None)``.
            config: Pursuit tuning. Defaults match the original pigeon script.
            on_status: Optional callback for each controller result.
        """
        cfg = config or TargetPursuitConfig()
        controller = TargetPursuitController(cfg)
        last_result = TargetPursuitResult(
            state=TargetPursuitState.ALIGNING,
            command=VelocityCommand(),
        )

        while True:
            scan = self.lidar.get_scan()
            if scan is None:
                await self.drone.set_velocity(VelocityCommand())
                await asyncio.sleep(0.05)
                continue

            loop_time = time.time()
            observation = tracker.latest(now=loop_time)
            result = controller.update(scan, observation, now=loop_time)
            last_result = result
            if on_status is not None:
                on_status(result)

            if result.done:
                await self.drone.set_velocity(VelocityCommand())
                return result

            if result.state == TargetPursuitState.SEARCHING:
                found = await self._run_target_search_sweep(tracker, cfg)
                await self.drone.set_velocity(VelocityCommand())
                if found:
                    controller.mark_reacquired()
                    continue

                lost = TargetPursuitResult(
                    state=TargetPursuitState.LOST,
                    command=VelocityCommand(),
                    done=True,
                    reason="search_failed",
                    elapsed_s=result.elapsed_s,
                )
                if on_status is not None:
                    on_status(lost)
                return lost

            await self.drone.set_velocity(result.command)
            await asyncio.sleep(0.05)

        return last_result

    async def _run_target_search_sweep(self, tracker, config: TargetPursuitConfig) -> bool:
        """Hover, rotate right, then rotate left until target is reacquired."""
        await self.drone.set_velocity(VelocityCommand())
        await asyncio.sleep(0.2)

        async def rotate_for(angle_deg: float, yaw_speed: float) -> bool:
            duration = abs(angle_deg / yaw_speed)
            cmd = VelocityCommand(yawspeed_deg_s=yaw_speed)
            start = asyncio.get_event_loop().time()
            while asyncio.get_event_loop().time() - start < duration:
                now = time.time()
                if tracker.latest(max_age_s=config.detection_miss_timeout_s, now=now) is not None:
                    return True

                scan = self.lidar.get_scan()
                if scan is not None:
                    if min(scan.left_distance(), scan.right_distance()) < config.min_wall_distance_m:
                        return False

                await self.drone.set_velocity(cmd)
                await asyncio.sleep(0.05)

            now = time.time()
            return tracker.latest(max_age_s=config.detection_miss_timeout_s, now=now) is not None

        if await rotate_for(config.search_right_deg, config.search_yaw_speed_deg_s):
            return True
        return await rotate_for(config.search_left_deg, -config.search_yaw_speed_deg_s)

    async def circuit(
        self,
        num_legs: int = 4,
        side: str = "left",
        target_distance: float = 2.0,
    ) -> bool:
        """Navigate a room perimeter: N legs of wall-follow separated by 90 rotations.

        Returns True if all legs completed.
        """
        for leg in range(num_legs):
            ok = await self.wall_follow(side=side, target_distance=target_distance)
            if not ok:
                return False
            if leg < num_legs - 1:
                await self.rotate(direction="right")
        return True
