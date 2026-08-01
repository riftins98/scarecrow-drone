"""The seam between mission logic and where it is flying.

WHY THIS EXISTS
The mission used to construct `GazeboLidar`, `GazeboCamera` and
`GazeboRangefinder` itself. That made the flight logic unrunnable anywhere but
simulation: putting it on the Raspberry Pi meant editing the mission. Since the
whole point of the `scarecrow` package is that the same code flies the real
drone, that was a hole in the design rather than a detail.

A `SensorSuite` answers "what am I flying, and how do I talk to its sensors".
The mission asks for a lidar; it never learns whether one came from a Gazebo
topic or a USB serial port.

TWO KINDS OF DIFFERENCE
1. **Sensors** -- same physical devices, different drivers. Fully hidden.
2. **World services** -- things only a simulator can do: knowing the true world
   pose of the drone, and deleting a bird from the world once it is reached.
   These have no hardware equivalent, so they are explicit capabilities that
   report themselves unsupported rather than being faked. On the real drone a
   reached pigeon flies away on its own; there is nothing to delete.

Keeping (2) visible is deliberate. Silently no-oping would let a mission look
like it removed a target when it did not.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from scarecrow.sensors.camera.base import CameraSource
from scarecrow.sensors.lidar.base import LidarSource
from scarecrow.sensors.rangefinder.base import RangefinderSource


@dataclass
class TargetRemovalOutcome:
    """Result of trying to remove a reached target from the world.

    ``supported`` distinguishes "there is nothing to remove here, by design"
    (hardware) from "removal was attempted and failed" (simulation). The
    mission logs them differently because only the second is a problem.
    """

    supported: bool
    success: bool
    message: str
    model_name: str | None = None
    world_name: str | None = None
    distance_m: float | None = None


class WorldServices(ABC):
    """Simulator-only capabilities, with honest hardware stand-ins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for logs, e.g. "gazebo" or "hardware"."""

    @abstractmethod
    def calibrate_frame(self, *, local_x: float, local_y: float, local_yaw_deg: float):
        """Tie the PX4 local frame to world coordinates.

        Returns a transform, or None where no external truth exists. The
        mission needs it only to localise a target for removal, so None simply
        disables that.
        """

    @abstractmethod
    def remove_target(
        self,
        *,
        x: float,
        y: float,
        name_prefixes: tuple[str, ...],
        uri_keywords: tuple[str, ...],
    ) -> TargetRemovalOutcome:
        """Remove the target nearest (x, y) from the world."""


class SensorSuite(ABC):
    """Creates and owns the drone's sensors for one environment.

    Bring-up is split into separate calls rather than one `start_all()`
    because the mission interleaves it with flight steps -- the lidar must be
    live before takeoff, while the camera is only needed once the drone is at
    altitude and past its ceiling check. Collapsing them would change flight
    ordering, which is exactly what this refactor must not do.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for logs, e.g. "gazebo" or "hardware"."""

    @property
    @abstractmethod
    def world(self) -> WorldServices:
        ...

    def prepare(self) -> None:
        """Begin any slow environment discovery. Non-blocking."""

    def await_prepared(self, *, timeout_s: float = 10.0) -> None:
        """Block until `prepare()` has finished."""

    def describe_environment(self) -> None:
        """Log what was discovered. Called once, after `await_prepared`."""

    @abstractmethod
    def start_lidar(self) -> LidarSource:
        """Start and return the 2D lidar (RPLidar A1M8)."""

    @abstractmethod
    def start_ceiling_rangefinder(self) -> RangefinderSource:
        """Start and return the upward rangefinder (TF-Luna).

        Raises RuntimeError with actionable text if it cannot start -- the
        mission derives its flight altitude from this sensor, so continuing
        without it is not safe.
        """

    @abstractmethod
    def start_camera(self) -> CameraSource:
        """Start and return the forward camera (Pi Camera 3)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop every started sensor. Safe to call more than once."""
