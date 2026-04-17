"""Flight orchestrator coordinating Drone, NavigationUnit, and optionally
camera/detection.

Provides a minimal lifecycle scaffold: preflight -> takeoff -> user-defined
mission body -> landing. The Flight class does NOT replace existing scripts
(`demo_flight.py`, `room_circuit.py`) -- they keep their proven procedural
structure. Flight is an alternative entry point for new missions that want
a reusable lifecycle pattern.

Usage:
    async def my_mission(flight):
        await flight.nav.wall_follow(side="left")
        await flight.nav.rotate()
        await flight.nav.wall_follow(side="left")

    flight = Flight(drone, lidar)
    await flight.run(my_mission, altitude=2.5)
"""
from __future__ import annotations

from typing import Awaitable, Callable, Optional

from ..drone import Drone
from ..navigation.navigation_unit import NavigationUnit
from ..sensors.camera.base import CameraSource
from ..sensors.lidar.base import LidarSource

MissionBody = Callable[["Flight"], Awaitable[None]]


class Flight:
    """Orchestrates a complete flight mission.

    Manages the lifecycle: connect -> arm -> takeoff -> mission body ->
    land -> disarm. The mission body is a user-supplied async function that
    receives the Flight instance and uses `flight.nav` / `flight.drone` to
    execute the actual behavior.

    Args:
        drone: Drone instance (will be connected if not already).
        lidar: Active LidarSource for navigation.
        camera: Optional CameraSource (for missions that record video).
        on_status: Optional callback(status: str) called on lifecycle changes.
    """

    def __init__(
        self,
        drone: Drone,
        lidar: LidarSource,
        camera: Optional[CameraSource] = None,
        on_status: Optional[Callable[[str], None]] = None,
    ):
        self.drone = drone
        self.lidar = lidar
        self.camera = camera
        self.nav = NavigationUnit(drone, lidar)
        self._on_status = on_status
        self.status: str = "idle"

    def _set_status(self, status: str) -> None:
        self.status = status
        if self._on_status is not None:
            try:
                self._on_status(status)
            except Exception:
                pass

    async def run(self, mission: MissionBody, altitude: float = 2.5) -> bool:
        """Execute the full lifecycle with the given mission body.

        Returns True on normal completion, False if any phase failed.
        On any exception, runs emergency_stop before re-raising.
        """
        try:
            self._set_status("connecting")
            if not await self.drone.connect():
                self._set_status("failed")
                return False

            self._set_status("health_check")
            if not await self.drone.wait_for_health():
                self._set_status("failed")
                return False

            await self.drone.set_ekf_origin()

            self._set_status("takeoff")
            if not await self.drone.takeoff(altitude):
                self._set_status("failed")
                return False

            if not await self.drone.start_offboard():
                self._set_status("failed")
                return False

            self._set_status("in_mission")
            await mission(self)

            self._set_status("landing")
            await self.drone.stop_offboard()
            await self.drone.land()

            self._set_status("completed")
            return True
        except Exception:
            self._set_status("failed")
            try:
                await self.drone.emergency_stop()
            except Exception:
                pass
            raise

    async def abort(self) -> None:
        """Emergency abort. Safe from any state."""
        self._set_status("aborted")
        await self.drone.emergency_stop()
