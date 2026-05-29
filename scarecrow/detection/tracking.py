"""Thread-safe target observation tracker for detector callbacks."""
from __future__ import annotations

import math
import threading
import time

from ..controllers.target_pursuit import TargetObservation


class TargetTracker:
    """Stores the latest high-confidence target detection.

    Designed to be passed as ``YoloDetector(on_detection_data=tracker.update_from_yolo)``.
    """

    def __init__(self, image_width: float = 1280.0) -> None:
        self.image_width = image_width
        self._lock = threading.Lock()
        self._observation: TargetObservation | None = None

    def update_from_yolo(self, detections: list[dict]) -> None:
        """Update from YoloDetector's list-of-dict detection payload."""
        if not detections:
            return

        best = max(detections, key=lambda d: d["conf"])
        cx, cy = best["center"]
        observation = TargetObservation(
            center_x=float(cx),
            center_y=float(cy),
            image_width=self.image_width,
            confidence=float(best["conf"]),
            timestamp=time.time(),
            class_name=best.get("class"),
            bbox=best.get("bbox"),
        )
        with self._lock:
            self._observation = observation

    def latest(self, max_age_s: float | None = None, now: float | None = None) -> TargetObservation | None:
        """Return the latest observation, optionally requiring freshness."""
        with self._lock:
            observation = self._observation

        if observation is None or max_age_s is None:
            return observation

        now_ts = time.time() if now is None else now
        if observation.age(now_ts) > max_age_s:
            return None
        return observation

    @property
    def age(self) -> float:
        """Seconds since the latest observation; inf if no target was seen."""
        with self._lock:
            observation = self._observation
        if observation is None:
            return math.inf
        return observation.age()
