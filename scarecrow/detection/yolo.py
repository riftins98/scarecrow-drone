"""YOLO-based object detection for drone camera frames.

Designed to be driven by a CameraSource on_frame callback.
Rate-limited to avoid saturating inference on high-fps sources.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Callable

import cv2
import numpy as np


class YoloDetector:
    """Runs YOLO inference on incoming camera frames.

    Callback-driven: set as ``camera.on_frame = detector.process_frame``
    or call ``process_frame(frame)`` directly. Rate-limited to at most
    one inference per ``min_interval`` seconds.

    Args:
        model_path: Path to the YOLO .pt weights file.
        output_dir: Directory for saving annotated detection images.
        confidence: Minimum detection confidence threshold.
        min_interval: Minimum seconds between inferences (rate limit).
        on_detection: Optional callback(img_path) called when a detection
                      image is saved — use for DB integration, UI updates, etc.
        on_detection_data: Optional callback(detections) called with raw
                      detection dictionaries for navigation controllers.
    """

    def __init__(
        self,
        model_path: str,
        output_dir: str,
        confidence: float = 0.3,
        min_interval: float = 1.0,
        on_detection: Callable[[str], None] | None = None,
        on_detection_data: Callable[[list[dict]], None] | None = None,
    ):
        self._model_path = model_path
        self.output_dir = output_dir
        self.detection_dir = os.path.join(output_dir, "detections")
        self.frames_dir = os.path.join(output_dir, "frames")
        self._confidence = confidence
        self._min_interval = min_interval
        self._on_detection = on_detection
        self._on_detection_data = on_detection_data
        self._save_detections = True
        self._save_no_detections = True
        self._detection_save_interval_s = 0.0
        self._max_saved_detections: int | None = None
        self._detection_save_prefix = "detection"
        self._saved_detection_count = 0
        self._last_detection_save_time = 0.0
        self._save_next_detection_reason: str | None = None
        self._save_next_frame_reason: str | None = None

        self.running = False
        self.detections_total = 0
        self.frames_processed = 0
        self._model = None
        self._detect_lock = threading.Lock()
        self._last_process_time = 0.0

    @property
    def on_detection_data(self) -> Callable[[list[dict]], None] | None:
        return self._on_detection_data

    @on_detection_data.setter
    def on_detection_data(self, callback: Callable[[list[dict]], None] | None) -> None:
        self._on_detection_data = callback

    @property
    def confidence(self) -> float:
        return self._confidence

    @confidence.setter
    def confidence(self, value: float) -> None:
        self._confidence = max(0.0, min(1.0, float(value)))

    def load_model(self) -> bool:
        """Pre-load YOLO model. Safe to call from a background thread."""
        print("Loading YOLO model...")
        try:
            os.environ.setdefault("YOLO_VERBOSE", "False")
            os.environ.setdefault("ULTRALYTICS_DISABLE_VERSION_CHECK", "1")
            logging.getLogger("ultralytics").setLevel(logging.WARNING)
            from ultralytics.models.yolo.model import YOLO
            self._model = YOLO(self._model_path, verbose=False)
            print("  YOLO model loaded.")
            return True
        except Exception as e:
            print(f"  YOLO load failed: {e}")
            return False

    def preload_async(self) -> threading.Thread:
        """Start `load_model()` in a background thread. Returns the thread.

        Use during MAVSDK connect to warm up the model in parallel. The caller
        must `thread.join()` before using the detector.
        """
        t = threading.Thread(target=self.load_model, daemon=True)
        t.start()
        return t

    def start(self) -> None:
        os.makedirs(self.detection_dir, exist_ok=True)
        os.makedirs(self.frames_dir, exist_ok=True)
        self.running = True

    def stop(self) -> None:
        self.running = False

    def configure_saving(
        self,
        *,
        save_detections: bool | None = None,
        save_no_detections: bool | None = None,
        detection_interval_s: float | None = None,
        max_saved_detections: int | None = None,
        detection_prefix: str | None = None,
        reset_counter: bool = False,
    ) -> None:
        """Configure which processed frames are written to disk.

        Inference and callbacks still run even when image saving is disabled.
        """
        if save_detections is not None:
            self._save_detections = save_detections
        if save_no_detections is not None:
            self._save_no_detections = save_no_detections
        if detection_interval_s is not None:
            self._detection_save_interval_s = max(0.0, float(detection_interval_s))
        self._max_saved_detections = max_saved_detections
        if detection_prefix is not None:
            self._detection_save_prefix = self._safe_reason(detection_prefix) or "detection"
        if reset_counter:
            self._saved_detection_count = 0
            self._last_detection_save_time = 0.0
            self._save_next_detection_reason = None
            self._save_next_frame_reason = None

    def capture_next_detection(self, reason: str = "manual") -> None:
        """Force-save the next frame that has an accepted detection."""
        self._save_next_detection_reason = reason

    def capture_next_frame(self, reason: str = "manual") -> None:
        """Force-save the next processed frame, with or without detections."""
        self._save_next_frame_reason = reason

    def _safe_reason(self, reason: str | None) -> str | None:
        if not reason:
            return None
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", reason.strip()).strip("_")
        return cleaned or None

    def _should_save_detection(self, now: float) -> tuple[bool, str | None]:
        forced_reason = self._save_next_frame_reason or self._save_next_detection_reason
        if forced_reason:
            self._save_next_frame_reason = None
            self._save_next_detection_reason = None
            return True, forced_reason
        if not self._save_detections:
            return False, None
        if (
            self._max_saved_detections is not None
            and self._saved_detection_count >= self._max_saved_detections
        ):
            return False, None
        if now - self._last_detection_save_time < self._detection_save_interval_s:
            return False, None
        return True, None

    def _save_detection_image(
        self,
        frame: np.ndarray,
        detections: list[dict],
        *,
        reason: str | None = None,
    ) -> str:
        annotated = frame.copy()
        for d in detections:
            x1, y1, x2, y2 = d['bbox']
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(annotated, f"{d['class']}: {d['conf']:.2f}",
                        (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.circle(annotated, d['center'], 5, (0, 0, 255), -1)

        prefix = self._safe_reason(reason) or "detection"
        img_path = os.path.join(
            self.detection_dir,
            f"{prefix}_{self.frames_processed:04d}.png",
        )
        cv2.imwrite(img_path, annotated)
        return img_path

    def _save_frame_image(self, frame: np.ndarray, *, reason: str | None = None) -> str:
        prefix = self._safe_reason(reason) or "frame"
        img_path = os.path.join(self.frames_dir, f"{prefix}_{self.frames_processed:04d}.png")
        cv2.imwrite(img_path, frame)
        return img_path

    def process_frame(self, frame: np.ndarray) -> None:
        """Process a single frame. Rate-limited and thread-safe.

        Designed to be called from CameraSource worker threads via on_frame.
        """
        if not self.running or self._model is None:
            return

        now = time.time()
        if not self._detect_lock.acquire(blocking=False):
            return
        try:
            if now - self._last_process_time < self._min_interval:
                return
            self._last_process_time = now
            self.frames_processed += 1
        finally:
            self._detect_lock.release()

        results = self._model(
            frame,
            conf=0.01,
            iou=0.45,
            imgsz=1280,
            verbose=False
        )

        detections = []
        best_candidate_conf = 0.0
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                best_candidate_conf = max(best_candidate_conf, conf)
                if conf < self._confidence:
                    continue
                cls_name = self._model.names[int(box.cls[0])]
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                detections.append({'class': cls_name, 'conf': conf,
                                   'bbox': (x1, y1, x2, y2), 'center': (cx, cy)})

        if detections:
            self.detections_total += len(detections)
            print(f"  [detection] Frame {self.frames_processed}: "
                  f"{len(detections)} detection(s) at {detections[0]['conf']:.0%}")

            should_save, save_reason = self._should_save_detection(now)
            if should_save:
                img_path = self._save_detection_image(
                    frame,
                    detections,
                    reason=save_reason or self._detection_save_prefix,
                )
                self._saved_detection_count += 1
                self._last_detection_save_time = now
                print(f"DETECTION_IMAGE:{img_path}", flush=True)

                if self._on_detection is not None:
                    self._on_detection(img_path)
            if self._on_detection_data is not None:
                self._on_detection_data(detections)
        else:
            if self._save_next_frame_reason:
                reason = self._save_next_frame_reason
                self._save_next_frame_reason = None
                self._save_frame_image(frame, reason=reason)
            elif self._save_no_detections:
                self._save_frame_image(frame)
            print(
                f"  [detection] Frame {self.frames_processed}: no detections "
                f"(best candidate {best_candidate_conf:.0%}, threshold {self._confidence:.0%})"
            )
