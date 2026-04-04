"""Background mapping task that fuses lidar scans with drone pose.

Runs as an asyncio coroutine alongside the flight script.
Polls MAVSDK telemetry (NED position + yaw) and the lidar's thread-safe
getter, then feeds each scan+pose pair into an OccupancyMap.

Usage:
    mapper = Mapper(lidar, drone)
    mapper_task = asyncio.create_task(mapper.run())

    # ... fly the room circuit ...

    mapper.stop()
    await mapper_task

    mapper.map.save_pdf("output/room_map.pdf", trajectory=mapper.trajectory)
    mapper.map.save_npz("output/room_map.npz", trajectory=mapper.trajectory)
"""
from __future__ import annotations

import asyncio
import math

from mavsdk import System

from ..sensors.lidar.base import LidarSource
from .occupancy_map import OccupancyMap


class Mapper:
    """Asyncio background task: poll drone pose + lidar → OccupancyMap.

    Args:
        lidar: An active LidarSource (must already be started).
        drone: Connected MAVSDK System (must be armed/flying when run() starts).
        resolution: Map resolution in meters/cell. Default 0.1m.
        size_m: Map side length in meters. Default 24m (2m margin around 20m room).
        origin_n: North coordinate of map bottom-left corner. Default -12m.
        origin_e: East coordinate of map bottom-left corner. Default -12m.
        poll_interval: Seconds between pose+scan samples. Default 0.1s (10Hz).
    """

    def __init__(
        self,
        lidar: LidarSource,
        drone: System,
        resolution: float = 0.1,
        size_m: float = 24.0,
        origin_n: float = -12.0,
        origin_e: float = -12.0,
        poll_interval: float = 0.1,
    ):
        self._lidar = lidar
        self._drone = drone
        self._poll_interval = poll_interval
        self._stop_flag = False
        self._paused = False
        self._map = OccupancyMap(
            resolution=resolution,
            size_m=size_m,
            origin_n=origin_n,
            origin_e=origin_e,
        )
        self._trajectory: list[tuple[float, float]] = []

    @property
    def map(self) -> OccupancyMap:
        """The accumulated occupancy map."""
        return self._map

    @property
    def trajectory(self) -> list[tuple[float, float]]:
        """List of (north_m, east_m) NED positions sampled during flight."""
        return self._trajectory

    def stop(self) -> None:
        """Signal run() to exit on the next iteration."""
        self._stop_flag = True

    def pause(self) -> None:
        """Pause map integration while keeping the task alive."""
        self._paused = True

    def resume(self) -> None:
        """Resume map integration after pause()."""
        self._paused = False

    async def run(self) -> None:
        """Asyncio task: continuously sample pose + lidar and update the map.

        Call asyncio.create_task(mapper.run()) before starting the flight,
        and mapper.stop() + await the task after the flight ends.
        """
        self._stop_flag = False
        samples = 0

        while not self._stop_flag:
            try:
                if self._paused:
                    await asyncio.sleep(self._poll_interval)
                    continue

                # One-shot NED position read
                north_m = east_m = None
                async for pos in self._drone.telemetry.position_velocity_ned():
                    north_m = pos.position.north_m
                    east_m = pos.position.east_m
                    break

                # One-shot yaw read
                yaw_rad = None
                async for att in self._drone.telemetry.attitude_euler():
                    yaw_rad = math.radians(att.yaw_deg)
                    break

                if north_m is None or east_m is None or yaw_rad is None:
                    await asyncio.sleep(self._poll_interval)
                    continue

                # Thread-safe lidar read (GazeboLidar uses threading.Lock internally)
                scan = self._lidar.get_scan()
                if scan is not None:
                    self._map.update(scan, north_m, east_m, yaw_rad)
                    self._trajectory.append((north_m, east_m))
                    samples += 1
                    if samples % 50 == 0:
                        print(
                            f"  [Mapper] {samples} samples | "
                            f"pos=({north_m:.1f}m N, {east_m:.1f}m E) "
                            f"yaw={math.degrees(yaw_rad):.0f}°"
                        )

            except Exception as exc:
                # Don't crash the flight on mapper errors — just skip the sample
                print(f"  [Mapper] warning: {exc}")

            await asyncio.sleep(self._poll_interval)

        print(f"  [Mapper] stopped. Total samples: {len(self._trajectory)}")
