"""Abstract camera interface and frame data structure."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Callable

import numpy as np


@dataclass
class CameraFrame:
    """A single camera frame.

    Attributes:
        image: BGR numpy array (H, W, 3).
        timestamp: Capture time (time.time()).
    """
    image: np.ndarray
    timestamp: float = field(default_factory=time.time)

    @property
    def height(self) -> int:
        return self.image.shape[0]

    @property
    def width(self) -> int:
        return self.image.shape[1]


class CameraSource(ABC):
    """Abstract base class for camera data sources.

    Implementations:
        - GazeboCamera: Gazebo simulation (gz topic polling + video recording)
        - (future) PiCameraSource: Real Pi Camera 3 hardware
    """

    @abstractmethod
    def start(self) -> None:
        """Start the camera data stream."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the camera data stream."""

    @abstractmethod
    def get_frame(self) -> CameraFrame | None:
        """Get the latest frame. Returns None if no data available yet."""

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
