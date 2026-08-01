"""Single-ray rangefinder support for Gazebo sensors."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import subprocess
import threading
import time

from ..gz_transport import GzSubscription, transport_available
from ..gz_utils import get_gz_env


@dataclass
class RangefinderReading:
    """A single rangefinder distance reading in meters."""

    distance_m: float
    timestamp: float = field(default_factory=time.time)


class GazeboRangefinder:
    """Reads a single-ray Gazebo lidar/rangefinder topic.

    This is for narrow range sensors such as the upward ceiling clearance
    sensor. The 2D RPLidar driver deliberately expects full-circle scans.
    """

    def __init__(
        self,
        topic: str | None = None,
        topic_hint: str = "ceiling_rangefinder/scan",
        env: dict | None = None,
    ):
        self._topic = topic
        self._topic_hint = topic_hint
        self._env = env or get_gz_env()
        self._latest_reading: RangefinderReading | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._subscription: GzSubscription | None = None

    @property
    def using_transport(self) -> bool:
        """True when reading via subscription rather than the CLI fallback."""
        return self._subscription is not None and self._subscription.active

    def start(self, *, discover_timeout_s: float = 15.0) -> None:
        if self._running:
            return
        deadline = time.time() + max(0.0, discover_timeout_s)
        while self._topic is None:
            self._topic = self._discover_topic()
            if self._topic is not None:
                break
            if time.time() >= deadline:
                break
            time.sleep(0.5)
        if self._topic is None:
            raise RuntimeError(
                f"Could not find rangefinder topic matching {self._topic_hint!r} "
                f"within {discover_timeout_s:.0f}s"
            )
        self._running = True

        if self._start_subscription():
            return

        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

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
        try:
            ranges = list(msg.ranges)
        except Exception:
            return
        if not ranges:
            return
        reading = self._reading_from_distance(float(ranges[0]))
        if reading is not None:
            with self._lock:
                self._latest_reading = reading

    def stop(self) -> None:
        self._running = False
        if self._subscription is not None:
            self._subscription.stop()
            self._subscription = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def get_reading(self) -> RangefinderReading | None:
        with self._lock:
            return self._latest_reading

    def get_distance_m(self) -> float | None:
        reading = self.get_reading()
        return None if reading is None else reading.distance_m

    @property
    def topic(self) -> str | None:
        return self._topic

    def _poll_loop(self) -> None:
        while self._running:
            try:
                result = subprocess.run(
                    ["gz", "topic", "-e", "-n", "1", "-t", self._topic],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=self._env,
                )
                if result.returncode != 0:
                    continue
                reading = self._parse_reading(result.stdout)
                if reading is not None:
                    with self._lock:
                        self._latest_reading = reading
            except Exception:
                pass

    def _discover_topic(self, topic_list: str | None = None) -> str | None:
        try:
            if topic_list is None:
                result = subprocess.run(
                    ["gz", "topic", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    env=self._env,
                )
                topic_list = result.stdout
            for line in topic_list.splitlines():
                topic = line.strip()
                if self._topic_hint in topic and "points" not in topic:
                    return topic
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_reading(text: str) -> RangefinderReading | None:
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("ranges:"):
                continue
            try:
                distance = float(line.split(":", 1)[1].strip())
            except ValueError:
                return None
            return GazeboRangefinder._reading_from_distance(distance)
        return None

    @staticmethod
    def _reading_from_distance(distance: float) -> RangefinderReading | None:
        """Validate one range value. Shared by both read paths.

        An out-of-range ray reads as inf and a miss can read as 0 or nan;
        either would be handed on as a real ceiling height, and this sensor
        sets the altitude ceiling.
        """
        if not math.isfinite(distance) or distance <= 0:
            return None
        return RangefinderReading(distance_m=distance)
