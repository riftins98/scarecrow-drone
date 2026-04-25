"""YOLO-based object detection for drone camera frames.

Designed to be driven by a CameraSource on_frame callback.
Rate-limited to avoid saturating inference on high-fps sources.
"""
from __future__ import annotations

import logging
import os
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
    """

    def __init__(
        self,
        model_path: str,
        output_dir: str,
        confidence: float = 0.3,
        min_interval: float = 1.0,
        on_detection: Callable[[str], None] | None = None,
    ):
        self._model_path = model_path
        self.output_dir = output_dir
        self.detection_dir = os.path.join(output_dir, "detections")
        self.frames_dir = os.path.join(output_dir, "frames")
        self._confidence = confidence
        self._min_interval = min_interval
        self._on_detection = on_detection

        self.running = False
        self.detections_total = 0
        self.frames_processed = 0
        self._model = None
        self._detect_lock = threading.Lock()
        self._last_process_time = 0.0

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
            conf=self._confidence,
            iou=0.45,
            imgsz=1280,
            verbose=False
        )

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                cls_name = self._model.names[int(box.cls[0])]
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                detections.append({'class': cls_name, 'conf': conf,
                                   'bbox': (x1, y1, x2, y2), 'center': (cx, cy)})

        if detections:
            self.detections_total += len(detections)
            print(f"  [detection] Frame {self.frames_processed}: "
                  f"{len(detections)} detection(s) at {detections[0]['conf']:.0%}")

            annotated = frame.copy()
            for d in detections:
                x1, y1, x2, y2 = d['bbox']
                cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(annotated, f"{d['class']}: {d['conf']:.2f}",
                            (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.circle(annotated, d['center'], 5, (0, 0, 255), -1)

            img_path = os.path.join(self.detection_dir,
                                    f"detection_{self.frames_processed:04d}.png")
            cv2.imwrite(img_path, annotated)
            print(f"DETECTION_IMAGE:{img_path}", flush=True)

            if self._on_detection is not None:
                self._on_detection(img_path)
        else:
            img_path = os.path.join(self.frames_dir, f"frame_{self.frames_processed:04d}.png")
            cv2.imwrite(img_path, frame)
            print(f"  [detection] Frame {self.frames_processed}: no detections")
