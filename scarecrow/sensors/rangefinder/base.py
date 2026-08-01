"""Abstract single-ray rangefinder interface.

This interface was missing: `GazeboRangefinder` was the only implementation and
the mission imported it by name, so there was nothing for a hardware driver to
implement against. The upward TF-Luna is what sets the mission's flight
altitude, so it is not an optional sensor.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time


@dataclass
class RangefinderReading:
    """A single distance sample.

    ``strength`` is the TF-Luna's return signal quality. Gazebo has no
    equivalent and leaves it None; on hardware a low value means the reading
    is untrustworthy even though a number came back.
    """

    distance_m: float
    timestamp: float = field(default_factory=time.time)
    strength: float | None = None


class RangefinderSource(ABC):
    """Abstract base for a single-ray distance sensor.

    Implementations:
        - GazeboRangefinder: gz topic polling
        - TFLunaRangefinder: TF-Luna over UART on the Raspberry Pi
    """

    @abstractmethod
    def start(self, *, discover_timeout_s: float = 15.0) -> None:
        """Begin acquiring readings."""

    @abstractmethod
    def stop(self) -> None:
        """Stop acquiring and release the device."""

    @abstractmethod
    def get_reading(self) -> RangefinderReading | None:
        """Latest reading, or None if nothing has arrived yet."""

    def get_distance_m(self) -> float | None:
        """Latest distance in meters, or None."""
        reading = self.get_reading()
        return None if reading is None else reading.distance_m

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
