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
    ) -> bool:
        """Follow a wall until front obstacle detected. Returns True if stopped
        normally, False on timeout."""
        ctrl = WallFollowController(
            side=side,
            target_distance=target_distance,
            forward_speed=forward_speed,
            front_stop_distance=front_stop_distance,
        )
        front_detector = FrontWallDetector(
            stop_distance_m=front_stop_distance,
        )

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
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

            if ctrl.done:
                await self.drone.set_velocity(VelocityCommand())
                return True
            await asyncio.sleep(0.05)

        await self.drone.set_velocity(VelocityCommand())
        return False

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
