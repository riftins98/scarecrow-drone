"""RPLidar A1M8 hardware lidar source — for the real drone.

Requires: pip install rplidar-roboticia
Connect: RPLidar A1M8 via USB → /dev/ttyUSB0 (Linux) or /dev/tty.usbserial (macOS)

TODO: Implement when hardware arrives. Interface matches GazeboLidar exactly.
"""
from __future__ import annotations

import math
import threading
import time

import numpy as np

from .base import LidarScan, LidarSource


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
            # scan = [(quality, angle_deg, distance_mm), ...]
            # Convert to sorted ranges array matching lidar_2d_v2 format
            if len(scan) < 10:
                continue

            # Sort by angle
            scan.sort(key=lambda p: p[1])

            # Convert to radians and meters
            angles_deg = np.array([p[1] for p in scan])
            distances_mm = np.array([p[2] for p in scan])

            angles_rad = np.deg2rad(angles_deg) - math.pi  # center at 0=forward
            distances_m = distances_mm / 1000.0

            # Resample to fixed 1080 bins matching simulation
            target_angles = np.linspace(-2.356195, 2.356195, 1080)
            resampled = np.interp(target_angles, angles_rad, distances_m,
                                  left=0.0, right=0.0)

            scan_obj = LidarScan(
                ranges=resampled.astype(np.float32),
                angle_min=-2.356195,
                angle_max=2.356195,
            )
            with self._lock:
                self._latest_scan = scan_obj
