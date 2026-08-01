"""Gazebo simulation lidar source — reads from gz topic."""
from __future__ import annotations

import os
import subprocess
import threading
import time

import numpy as np

from .base import LidarScan, LidarSource
from ..gz_transport import GzSubscription, transport_available
from ..gz_utils import get_gz_env


class GazeboLidar(LidarSource):
    """Reads 2D lidar data from a Gazebo simulation topic.

    Prefers an in-process gz-transport subscription. Falls back to polling
    `gz topic -e -n 1` on background threads when the Python bindings are not
    importable.

    The fallback is what this class used to do always, and it is expensive in a
    way that matters here: the control loop reads this sensor every iteration,
    so a fork+exec per scan put the flight loop's cost into process creation.
    See scarecrow.sensors.gz_transport for the measurements.

    Args:
        topic: Full Gazebo topic path. If None, auto-discovers.
        env: Environment variables for gz CLI. If None, auto-detects.
        num_threads: Polling threads for the CLI fallback only. Ignored when
            the subscription path is available, which needs no threads of its
            own -- gz-transport delivers on its own.
    """

    def __init__(
        self,
        topic: str | None = None,
        env: dict | None = None,
        num_threads: int = 2,
    ):
        self._topic = topic
        self._env = env or get_gz_env()
        self._num_threads = num_threads
        self._latest_scan: LidarScan | None = None
        self._lock = threading.Lock()
        self._running = False
        self._threads: list[threading.Thread] = []
        self._subscription: GzSubscription | None = None

    @property
    def using_transport(self) -> bool:
        """True when reading via subscription rather than the CLI fallback."""
        return self._subscription is not None and self._subscription.active

    def start(self) -> None:
        if self._running:
            return
        if self._topic is None:
            self._topic = self._discover_topic()
        if self._topic is None:
            raise RuntimeError("Could not find lidar_2d_v2 topic in Gazebo")
        self._running = True

        if self._start_subscription():
            return

        for _ in range(self._num_threads):
            t = threading.Thread(target=self._poll_loop, daemon=True)
            t.start()
            self._threads.append(t)

    def _start_subscription(self) -> bool:
        if not transport_available():
            return False
        try:
            from gz.msgs10.laserscan_pb2 import LaserScan
        except Exception:
            return False
        sub = GzSubscription(self._topic, LaserScan, self._on_scan, env=self._env)
        if not sub.start():
            return False
        self._subscription = sub
        return True

    def _on_scan(self, msg) -> None:
        scan = self._scan_from_proto(msg)
        if scan is not None:
            with self._lock:
                self._latest_scan = scan

    def stop(self) -> None:
        self._running = False
        if self._subscription is not None:
            self._subscription.stop()
            self._subscription = None
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

    def _discover_topic(self, topic_list: str | None = None) -> str | None:
        """Find the lidar_2d_v2 scan topic from Gazebo.

        Args:
            topic_list: Pre-fetched `gz topic -l` output. If None, runs it now.
                Passing a cached value avoids a slow subprocess call during startup.

        Filters out '/points' variant -- we want the 2D range scan, not the
        point cloud.
        """
        try:
            if topic_list is None:
                result = subprocess.run(
                    ["gz", "topic", "-l"],
                    capture_output=True, text=True, timeout=5, env=self._env,
                )
                topic_list = result.stdout
            for line in topic_list.split('\n'):
                if "lidar_2d_v2/scan" in line and "points" not in line:
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

        Returns None for malformed/incompatible scan metadata. This project
        expects full-circle 360° scans.
        """
        ranges = []
        angle_min = None
        angle_max = None
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('angle_min:'):
                try:
                    angle_min = float(line.split(':', 1)[1].strip())
                except ValueError:
                    pass
                continue
            if line.startswith('angle_max:'):
                try:
                    angle_max = float(line.split(':', 1)[1].strip())
                except ValueError:
                    pass
                continue
            if line.startswith('ranges:'):
                try:
                    val = float(line.split(':', 1)[1].strip())
                    ranges.append(val)
                except ValueError:
                    ranges.append(float('inf'))
        return GazeboLidar._build_scan(ranges, angle_min, angle_max)

    @staticmethod
    def _scan_from_proto(msg) -> LidarScan | None:
        """Build a LidarScan from a gz.msgs LaserScan.

        Goes through the same validation as the text parser on purpose: the
        360-degree contract is a property of what this project's controllers
        assume about the sensor, not of how the bytes arrived. A scan that the
        CLI path would have rejected must not slip through here.
        """
        try:
            return GazeboLidar._build_scan(
                list(msg.ranges), float(msg.angle_min), float(msg.angle_max)
            )
        except Exception:
            return None

    @staticmethod
    def _build_scan(
        ranges: list, angle_min: float | None, angle_max: float | None
    ) -> LidarScan | None:
        """Validate and wrap raw scan values. Shared by both read paths."""
        if not ranges:
            return None
        if angle_min is None or angle_max is None:
            return None

        # Strict 360° contract (allow tiny numeric drift from parser/source).
        angle_span = angle_max - angle_min
        if not (2.0 * np.pi - 0.05 <= angle_span <= 2.0 * np.pi + 0.05):
            return None

        return LidarScan(
            ranges=np.array(ranges, dtype=np.float32),
            angle_min=angle_min,
            angle_max=angle_max,
        )
