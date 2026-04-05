"""Abstract lidar interface and scan data structure."""
from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np


@dataclass
class LidarScan:
    """A single 2D lidar scan.

    Attributes:
        ranges: Distance measurements in meters (len = num_samples).
        angle_min: Start angle in radians.
        angle_max: End angle in radians.
        timestamp: Capture time (time.time()).

    Contract:
        All scans in this project are full-circle 360° with
        angle_min=-pi and angle_max=+pi.
    """
    ranges: np.ndarray
    angle_min: float = -math.pi
    angle_max: float = math.pi
    timestamp: float = field(default_factory=time.time)

    @property
    def num_samples(self) -> int:
        return len(self.ranges)

    @property
    def angles(self) -> np.ndarray:
        """Angle for each range sample in radians."""
        return np.linspace(self.angle_min, self.angle_max, self.num_samples)

    @property
    def angle_increment(self) -> float:
        if self.num_samples < 2:
            return 0.0
        return (self.angle_max - self.angle_min) / (self.num_samples - 1)

    def get_range_at_angle(self, angle_rad: float) -> float:
        """Get the range measurement closest to the given angle."""
        if self.num_samples == 0:
            return float('inf')
        idx = int(round((angle_rad - self.angle_min) / self.angle_increment))
        idx = max(0, min(idx, self.num_samples - 1))
        return float(self.ranges[idx])

    def get_sector_min(self, start_angle: float, end_angle: float) -> float:
        """Get the minimum range within an angular sector.

        Args:
            start_angle: Sector start in radians.
            end_angle: Sector end in radians.

        Returns:
            Minimum distance in the sector, or inf if no valid readings.
        """
        if self.num_samples == 0:
            return float('inf')
        angles = self.angles
        mask = self._sector_mask(angles, start_angle, end_angle)
        sector = self.ranges[mask]
        valid = sector[(sector > 0.1) & (sector < 30.0)]
        if len(valid) == 0:
            return float('inf')
        return float(np.min(valid))

    def get_sector_mean(self, start_angle: float, end_angle: float) -> float:
        """Get the mean range within an angular sector."""
        if self.num_samples == 0:
            return float('inf')
        angles = self.angles
        mask = self._sector_mask(angles, start_angle, end_angle)
        sector = self.ranges[mask]
        valid = sector[(sector > 0.1) & (sector < 30.0)]
        if len(valid) == 0:
            return float('inf')
        return float(np.mean(valid))

    @staticmethod
    def _sector_mask(angles: np.ndarray, start_angle: float, end_angle: float) -> np.ndarray:
        """Build a sector mask, including wrap-around sectors across ±pi."""
        if start_angle <= end_angle:
            return (angles >= start_angle) & (angles <= end_angle)
        return (angles >= start_angle) | (angles <= end_angle)

    # Convenience directions (body frame: 0=forward, +90=left, -90=right)
    # Angles in the lidar frame: 0=forward, positive=left (CCW)
    FORWARD = 0.0
    LEFT = math.pi / 2       # +90 deg
    RIGHT = -math.pi / 2     # -90 deg
    REAR = math.pi            # 180 deg

    def get_wall_alignment_error(self, center_angle: float, half_width: float = 0.35) -> float | None:
        """Measure how many radians the drone is rotated away from being
        parallel to a wall.

        Extracts lidar points in a sector, fits a line via SVD, and returns
        the signed angle between the wall direction and the drone's forward
        axis. A wall to the left should run parallel to forward (0°).

        Args:
            center_angle: Center of the wall sector (radians). Use LEFT for left wall.
            half_width: Half-width of the sector (radians). Default ±20°.

        Returns:
            Signed error in radians. 0 = perfectly parallel.
            Positive = need to turn clockwise (right) to align.
            Negative = need to turn counter-clockwise (left).
            None if not enough points.
        """
        if self.num_samples == 0:
            return None

        angles = self.angles
        mask = (
            (angles >= center_angle - half_width)
            & (angles <= center_angle + half_width)
            & (self.ranges > 0.1)
            & (self.ranges < 30.0)
        )
        sector_ranges = self.ranges[mask]
        sector_angles = angles[mask]

        if len(sector_ranges) < 10:
            return None

        # Convert polar to Cartesian (body frame)
        x = sector_ranges * np.cos(sector_angles)
        y = sector_ranges * np.sin(sector_angles)
        points = np.column_stack((x, y))

        # Fit line via SVD (Total Least Squares)
        centered = points - points.mean(axis=0)
        _, _, vt = np.linalg.svd(centered)
        wall_dir = vt[0]  # principal component = direction along the wall

        # Wall direction angle relative to forward (body X axis)
        angle = math.atan2(wall_dir[1], wall_dir[0])

        # Resolve 180° ambiguity: bring to range -π/2 .. +π/2
        # A wall parallel to forward has direction ≈ 0° or ≈ 180° (same line)
        if angle > math.pi / 2:
            angle -= math.pi
        elif angle < -math.pi / 2:
            angle += math.pi

        return angle

    def get_front_wall_tilt(self, spread: float = 0.25) -> float | None:
        """Measure how many degrees the front wall tilts from perpendicular.

        Uses two symmetric range measurements left and right of center.
        No SVD, no ambiguity — pure geometry.

        Args:
            spread: Half-angle between the two measurement rays (radians).
                    Default 0.25 rad ≈ 14°.

        Returns:
            Tilt in radians. 0 = perfectly perpendicular.
            Positive = wall tilts clockwise (drone angled left).
            None if no valid measurements.
        """
        r_left = self.get_range_at_angle(spread)     # slightly left of center
        r_right = self.get_range_at_angle(-spread)    # slightly right of center

        if r_left > 25.0 or r_right > 25.0 or r_left < 0.2 or r_right < 0.2:
            return None

        # Geometry: two rays at ±spread hitting a tilted wall
        # tilt = atan((r_left - r_right) / ((r_left + r_right) * tan(spread)))
        tan_spread = math.tan(spread)
        tilt = math.atan2(r_left - r_right, (r_left + r_right) * tan_spread)
        return tilt

    def left_wall_angle_error(self) -> float | None:
        """How many radians off from being parallel to the left wall."""
        return self.get_wall_alignment_error(self.LEFT)

    def right_wall_angle_error(self) -> float | None:
        """How many radians off from being parallel to the right wall."""
        return self.get_wall_alignment_error(self.RIGHT)

    def front_distance(self, half_width: float = 0.15) -> float:
        """Minimum distance in the forward sector."""
        return self.get_sector_min(self.FORWARD - half_width, self.FORWARD + half_width)

    def left_distance(self, half_width: float = 0.15) -> float:
        """Minimum distance to the left."""
        return self.get_sector_min(self.LEFT - half_width, self.LEFT + half_width)

    def right_distance(self, half_width: float = 0.15) -> float:
        """Minimum distance to the right."""
        return self.get_sector_min(self.RIGHT - half_width, self.RIGHT + half_width)

    def rear_distance(self, half_width: float = 0.15) -> float:
        """Minimum distance to the rear (around ±180°)."""
        return self.get_sector_min(math.pi - half_width, -math.pi + half_width)


class LidarSource(ABC):
    """Abstract base class for lidar data sources.

    Implementations:
        - GazeboLidar: Gazebo simulation (gz topic polling)
        - RPLidarSource: Real RPLidar A1M8 hardware (USB serial)
    """

    @abstractmethod
    def start(self) -> None:
        """Start the lidar data stream."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the lidar data stream."""

    @abstractmethod
    def get_scan(self) -> LidarScan | None:
        """Get the latest scan. Returns None if no data available yet."""

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
