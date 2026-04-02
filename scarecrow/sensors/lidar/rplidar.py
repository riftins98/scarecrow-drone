"""RPLidar A1M8 hardware lidar source — for the real drone.

Requires: pip install rplidar-roboticia
Connect: RPLidar A1M8 via USB → /dev/ttyUSB0 (Linux) or /dev/tty.usbserial (macOS)

Output contract is unified with simulation:
    - 1440 samples
    - angle_min=-pi, angle_max=+pi (full 360°)
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from .base import LidarScan, LidarSource


ANGLE_MIN = -math.pi
ANGLE_MAX = math.pi
TARGET_SAMPLES = 1440


class RPLidarSource(LidarSource):
    """Reads from a real RPLidar A1M8 via USB serial.

    Args:
        port: Serial port path.
        baudrate: Serial baud rate (default 115200 for A1M8).
    """

    def __init__(self, port: str = "/dev/ttyUSB0", baudrate: int = 115200):
        self._port = port
        self._baudrate = baudrate
        self._lidar = None
        self._latest_scan: LidarScan | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        try:
            from rplidar import RPLidar
        except ImportError:
            raise ImportError(
                "rplidar package not installed. Run: pip install rplidar-roboticia"
            )
        self._lidar = RPLidar(self._port, baudrate=self._baudrate)
        self._running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._lidar:
            self._lidar.stop()
            self._lidar.disconnect()
            self._lidar = None

    def get_scan(self) -> LidarScan | None:
        with self._lock:
            return self._latest_scan

    def _scan_loop(self) -> None:
        """Continuously read scans from the RPLidar."""
        for scan in self._lidar.iter_scans():
            if not self._running:
                break
            scan_obj = self._convert_scan(scan)
            if scan_obj is None:
                continue
            with self._lock:
                self._latest_scan = scan_obj

    @staticmethod
    def _convert_scan(scan_points: list[tuple[int, float, float]]) -> LidarScan | None:
        """Convert raw RPLidar points into a fixed 360° `LidarScan`.

        Args:
            scan_points: Sequence of (quality, angle_deg, distance_mm).

        Returns:
            LidarScan in unified full-circle format, or None if insufficient data.
        """
        if len(scan_points) < 10:
            return None

        pts = sorted(scan_points, key=lambda p: p[1])
        angles_deg = np.array([p[1] for p in pts], dtype=np.float64)
        distances_mm = np.array([p[2] for p in pts], dtype=np.float64)

        valid = distances_mm > 0.0
        if np.count_nonzero(valid) < 10:
            return None

        angles_deg = angles_deg[valid]
        distances_m = (distances_mm[valid] / 1000.0)

        # Map native 0..360° to body frame -pi..pi with 0=forward.
        angles_rad = np.deg2rad(angles_deg) - math.pi

        # Periodic extension avoids edge artifacts at -pi/pi seam.
        angles_ext = np.concatenate((angles_rad[-1:] - 2 * math.pi, angles_rad, angles_rad[:1] + 2 * math.pi))
        ranges_ext = np.concatenate((distances_m[-1:], distances_m, distances_m[:1]))

        target_angles = np.linspace(ANGLE_MIN, ANGLE_MAX, TARGET_SAMPLES)
        resampled = np.interp(target_angles, angles_ext, ranges_ext)

        return LidarScan(
            ranges=resampled.astype(np.float32),
            angle_min=ANGLE_MIN,
            angle_max=ANGLE_MAX,
        )
