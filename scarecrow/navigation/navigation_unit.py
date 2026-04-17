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

from ..controllers.distance_stabilizer import DistanceTargets
from ..controllers.front_wall_detector import FrontWallDetector
from ..controllers.rotation import rotate_90
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
