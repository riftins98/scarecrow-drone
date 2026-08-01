"""Raspberry Pi Camera Module 3 source, for the real drone.

Mirrors `GazeboCamera`'s contract exactly -- `start`/`stop`/`get_frame` plus an
`on_frame` callback that the YOLO detector attaches to -- so
`DetectionSession` and the mission cannot tell the two apart.

PI SETUP
Camera Module 3 needs libcamera and picamera2, which are system packages, not
pip wheels:
    sudo apt install -y python3-picamera2
If the flight code runs in a virtualenv, create it with --system-site-packages
or picamera2 will not be importable.

WHY BGR
Every downstream consumer -- YOLO, OpenCV, the detection frame writer --
expects BGR, which is what Gazebo already delivers. picamera2 hands back RGB,
so this driver converts once at the source. Skipping that does not error: it
silently swaps red and blue, and a YOLO model trained on BGR quietly loses
accuracy with nothing in the logs to explain it.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from .base import CameraFrame, CameraSource

# Matches the simulated mono_cam so the detector sees the same geometry in both
# environments -- bbox-width range estimation in the pursuit entry planner is
# calibrated against this width.
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_FPS = 15


class PiCameraSource(CameraSource):
    """Pi Camera Module 3 via picamera2.

    Keeps only the newest frame. Detection is slower than capture, so a queue
    would grow without bound and the detector would fall progressively further
    behind the drone's actual position -- pursuing where the bird was, not
    where it is.
    """

    def __init__(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
    ) -> None:
        self._width = width
        self._height = height
        self._fps = fps
        self._camera = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._latest: CameraFrame | None = None
        # Set by DetectionSession before start(); mirrors GazeboCamera.
        self.on_frame = None

    @property
    def topic(self) -> str:
        """Human-readable source name. Named `topic` to mirror GazeboCamera."""
        return f"picamera3({self._width}x{self._height}@{self._fps})"

    def start(self) -> None:
        """Configure and start the camera, then begin the capture loop."""
        try:
            from picamera2 import Picamera2
        except ImportError as exc:  # pragma: no cover - depends on host
            raise RuntimeError(
                "picamera2 is required for the Pi Camera: "
                "sudo apt install -y python3-picamera2 "
                "(and create the venv with --system-site-packages)"
            ) from exc

        self._camera = Picamera2()
        config = self._camera.create_video_configuration(
            main={"size": (self._width, self._height), "format": "RGB888"},
            controls={"FrameRate": self._fps},
        )
        self._camera.configure(config)
        self._camera.start()
        # Auto-exposure and auto-white-balance need a moment to converge; the
        # first frames are otherwise dark enough to hurt detection.
        time.sleep(1.0)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._camera is not None:
            try:
                self._camera.stop()
                self._camera.close()
            except Exception:
                pass
            self._camera = None

    def get_frame(self) -> CameraFrame | None:
        with self._lock:
            return self._latest

    def _capture_loop(self) -> None:  # pragma: no cover - requires hardware
        interval = 1.0 / max(1, self._fps)
        while self._running:
            started = time.time()
            try:
                rgb = self._camera.capture_array()
                image = self._to_bgr(rgb)
                frame = CameraFrame(image=image)
                with self._lock:
                    self._latest = frame
                if self.on_frame is not None:
                    self.on_frame(image)
            except Exception:
                # One bad capture must not stop the stream. The detector sees a
                # stale frame and the pursuit controller's own miss-timeout
                # handles a genuinely dead camera.
                time.sleep(0.05)

            elapsed = time.time() - started
            if elapsed < interval:
                time.sleep(interval - elapsed)

    @staticmethod
    def _to_bgr(rgb: np.ndarray) -> np.ndarray:
        """RGB -> BGR without requiring OpenCV.

        Pure, so the channel order is unit-testable without a camera. Getting
        this wrong is silent: detection accuracy drops and nothing logs.
        """
        return rgb[:, :, ::-1].copy()
