"""Gazebo simulation lidar source — reads from gz topic."""
from __future__ import annotations

import os
import subprocess
import threading
import time

import numpy as np

from .base import LidarScan, LidarSource


class GazeboLidar(LidarSource):
    """Reads 2D lidar data from a Gazebo simulation topic.

    Uses background threads to poll `gz topic -e -n 1` for continuous data.
    This is a macOS workaround — on Linux, use gz-transport Python bindings
    for lower latency.

    Args:
        topic: Full Gazebo topic path. If None, auto-discovers.
        env: Environment variables for gz CLI. If None, auto-detects.
        num_threads: Number of parallel polling threads (more = higher fps).
    """

    def __init__(
        self,
        topic: str | None = None,
        env: dict | None = None,
        num_threads: int = 2,
    ):
        self._topic = topic
        self._env = env or self._detect_gz_env()
        self._num_threads = num_threads
        self._latest_scan: LidarScan | None = None
        self._lock = threading.Lock()
        self._running = False
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._running:
            return
        if self._topic is None:
            self._topic = self._discover_topic()
        if self._topic is None:
            raise RuntimeError("Could not find lidar_2d_v2 topic in Gazebo")
        self._running = True
        for _ in range(self._num_threads):
            t = threading.Thread(target=self._poll_loop, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=3)
        self._threads.clear()

    def get_scan(self) -> LidarScan | None:
        with self._lock:
            return self._latest_scan

    @property
    def topic(self) -> str | None:
        return self._topic

    def _poll_loop(self) -> None:
        while self._running:
            try:
                result = subprocess.run(
                    ["gz", "topic", "-e", "-n", "1", "-t", self._topic],
                    capture_output=True, text=True, timeout=5, env=self._env,
                )
                if result.returncode != 0:
                    continue
                scan = self._parse_scan(result.stdout)
                if scan is not None:
                    with self._lock:
                        self._latest_scan = scan
            except Exception:
                pass

    @staticmethod
    def _detect_gz_env() -> dict:
        """Auto-detect Gazebo environment (GZ_IP, GZ_PARTITION)."""
        env = os.environ.copy()

        # Try without GZ_IP first (works in non-standalone/GUI mode)
        try:
            result = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True, text=True, timeout=3, env=env,
            )
            if "holybro_x500" in result.stdout:
                return env
        except Exception:
            pass

        # Try with GZ_IP (needed in standalone mode with GZ_PARTITION)
        try:
            result = subprocess.run(
                ["ipconfig", "getifaddr", "en0"],
                capture_output=True, text=True, timeout=3,
            )
            env["GZ_IP"] = result.stdout.strip()
        except Exception:
            try:
                result = subprocess.run(
                    ["hostname", "-I"],
                    capture_output=True, text=True, timeout=3,
                )
                env["GZ_IP"] = result.stdout.strip().split()[0]
            except Exception:
                pass
        env["GZ_PARTITION"] = "px4"
        return env

    def _discover_topic(self) -> str | None:
        """Find the lidar_2d_v2 scan topic from Gazebo."""
        try:
            result = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True, text=True, timeout=5, env=self._env,
            )
            for line in result.stdout.split('\n'):
                if "lidar_2d_v2/scan" in line:
                    return line.strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_scan(text: str) -> LidarScan | None:
        """Parse gz topic text output into a LidarScan.

        Keeps ALL range values to preserve angle-to-index mapping.
        Invalid ranges (0 or inf) are kept as-is — filtering happens
        in LidarScan methods (get_sector_min, get_wall_alignment_error, etc).
        """
        ranges = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('ranges:'):
                try:
                    val = float(line.split(':')[1].strip())
                    ranges.append(val)
                except ValueError:
                    ranges.append(float('inf'))
        if not ranges:
            return None
        return LidarScan(
            ranges=np.array(ranges, dtype=np.float32),
            angle_min=-2.356195,
            angle_max=2.356195,
        )
