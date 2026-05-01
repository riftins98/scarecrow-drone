"""Gazebo simulation camera source — reads from gz topic.

Mirrors the GazeboLidar pattern: background threads poll ``gz topic -e -n 1``
for continuous frame data. Also supports recording raw frames to disk and
building an MP4 video with ffmpeg after the flight.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import threading
import time

import cv2
import numpy as np

from .base import CameraFrame, CameraSource
from ..gz_utils import get_gz_env


def parse_gz_frame(raw: bytes) -> np.ndarray | None:
    """Parse raw gz topic binary output into a BGR numpy array.

    Handles the Gazebo protobuf text format with embedded image data.
    Uses rfind for the closing quote to avoid stopping at embedded quote bytes.
    """
    if len(raw) < 100:
        return None

    text = raw.decode('latin-1', errors='replace')
    width = height = 0
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('width:'):
            try: width = int(line.split(':')[1].strip())
            except: pass
        elif line.startswith('height:'):
            try: height = int(line.split(':')[1].strip())
            except: pass

    if width == 0 or height == 0:
        return None

    expected = width * height * 3

    data_start = raw.find(b'data: "') + 7
    data_end = raw.rfind(b'"')
    if data_start <= 7 or data_end <= data_start:
        return None

    chunk = raw[data_start:data_end]

    try:
        frame_bytes = chunk.decode('unicode_escape').encode('latin-1')
    except UnicodeDecodeError:
        result_bytes = bytearray()
        pos = 0
        while pos < len(chunk):
            try:
                part = chunk[pos:].decode('unicode_escape').encode('latin-1')
                result_bytes.extend(part)
                break
            except UnicodeDecodeError as e:
                good = chunk[pos:pos+e.start].decode('unicode_escape').encode('latin-1')
                result_bytes.extend(good)
                result_bytes.append(chunk[pos+e.start])
                pos += e.start + 1
        frame_bytes = bytes(result_bytes)

    if len(frame_bytes) < expected:
        return None

    try:
        pixels = np.frombuffer(frame_bytes[:expected], dtype=np.uint8).reshape((height, width, 3))
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


class GazeboCamera(CameraSource):
    """Reads camera frames from a Gazebo simulation topic.

    Uses background threads to poll ``gz topic -e -n 1`` for continuous data.
    This is a macOS workaround — on Linux, use gz-transport Python bindings
    for lower latency.

    Also supports recording raw frames to disk and building a video after
    landing via ``start_recording()`` / ``stop_recording()`` / ``save_video()``.

    Shares parsed frames with external consumers via the ``on_frame``
    callback (e.g. for live YOLO detection during recording).

    Args:
        topic: Full Gazebo topic path. If None, auto-discovers.
        env: Environment variables for gz CLI. If None, auto-detects.
        num_threads: Number of parallel polling threads (more = higher fps).
    """

    def __init__(
        self,
        topic: str | None = None,
        env: dict | None = None,
        num_threads: int = 4,
    ):
        self._topic = topic
        self._env = env or get_gz_env()
        self._num_threads = num_threads
        self._latest_frame: CameraFrame | None = None
        self._lock = threading.Lock()
        self._running = False
        self._threads: list[threading.Thread] = []
        self.on_frame = None   # callback(frame: np.ndarray) — set before start()

        # Recording state
        self._recording = False
        self._record_dir: str | None = None
        self._output_dir: str | None = None
        self._frame_count = 0
        self._record_start: float | None = None
        self._record_stop: float | None = None

    def start(self) -> None:
        if self._running:
            return
        if self._topic is None:
            self._topic = self._discover_topic()
        if self._topic is None:
            raise RuntimeError("Could not find camera topic in Gazebo")
        self._running = True
        for _ in range(self._num_threads):
            t = threading.Thread(target=self._poll_loop, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._running = False
        self._recording = False
        for t in self._threads:
            t.join(timeout=3)
        self._threads.clear()

    def get_frame(self) -> CameraFrame | None:
        with self._lock:
            return self._latest_frame

    @property
    def topic(self) -> str | None:
        return self._topic

    def start_recording(self, output_dir: str) -> None:
        """Begin saving raw frames to disk for later video build."""
        self._output_dir = output_dir
        self._record_dir = os.path.join(output_dir, ".camera_raw")
        os.makedirs(self._record_dir, exist_ok=True)
        self._frame_count = 0
        self._record_start = time.time()
        self._recording = True
        print(f"  [camera] Recording...")

    def stop_recording(self) -> None:
        """Stop saving raw frames."""
        self._recording = False
        self._record_stop = time.time()
        print(f"  [camera] Captured {self._frame_count} raw frames")

    def _poll_loop(self) -> None:
        while self._running:
            try:
                result = subprocess.run(
                    ["gz", "topic", "-e", "-n", "1", "-t", self._topic],
                    capture_output=True, timeout=8, env=self._env,
                )
                if result.returncode != 0 or len(result.stdout) < 100000:
                    continue

                image = parse_gz_frame(result.stdout)
                if image is None:
                    continue

                # Update latest frame
                frame = CameraFrame(image=image)
                with self._lock:
                    self._latest_frame = frame

                # Save raw to disk if recording
                if self._recording and self._record_dir:
                    with self._lock:
                        n = self._frame_count
                        self._frame_count += 1
                    outfile = os.path.join(self._record_dir, f"raw_{n:04d}.bin")
                    with open(outfile, 'wb') as f:
                        f.write(result.stdout)

                # Share with consumer callback
                if self.on_frame is not None:
                    self.on_frame(image)

            except Exception:
                pass

    def _discover_topic(self) -> str | None:
        """Find the camera image topic from Gazebo."""
        try:
            result = subprocess.run(
                ["gz", "topic", "-l"],
                capture_output=True, text=True, timeout=5, env=self._env,
            )
            topics = [line.strip() for line in result.stdout.split('\n') if line.strip()]

            # Prefer the drone-mounted camera explicitly.
            for line in topics:
                if "camera_link/sensor/camera/image" in line and "/model/holybro_x500" in line:
                    return line

            # Fallback: any camera topic, but avoid fixed monitoring cameras if possible.
            for line in topics:
                if "camera_link/sensor/camera/image" not in line:
                    continue
                if "/model/fixed_cam" in line or "/model/mono_cam_hd" in line:
                    continue
                return line
        except Exception:
            pass
        return None

    def save_video(self) -> str | None:
        """Parse raw dumps into PNGs, stitch into MP4 with ffmpeg.

        Call after stop_recording(). Returns the video path or None.
        """
        if not self._record_dir or not self._output_dir:
            return None

        raw_files = sorted(glob.glob(os.path.join(self._record_dir, "raw_*.bin")))
        if not raw_files:
            print("  [camera] No frames captured")
            return None

        png_dir = os.path.join(self._output_dir, ".camera_png")
        os.makedirs(png_dir, exist_ok=True)
        good = 0

        for rawfile in raw_files:
            try:
                with open(rawfile, 'rb') as f:
                    raw = f.read()
                frame = parse_gz_frame(raw)
                if frame is not None:
                    cv2.imwrite(os.path.join(png_dir, f"frame_{good:04d}.png"), frame)
                    good += 1
            except Exception:
                pass

        print(f"  [camera] Decoded {good}/{len(raw_files)} frames")

        if good == 0:
            print("  [camera] No valid frames")
            shutil.rmtree(self._record_dir, ignore_errors=True)
            shutil.rmtree(png_dir, ignore_errors=True)
            return None

        shutil.copy2(
            os.path.join(png_dir, "frame_0000.png"),
            os.path.join(self._output_dir, "camera_ground.png")
        )
        shutil.copy2(
            os.path.join(png_dir, f"frame_{good-1:04d}.png"),
            os.path.join(self._output_dir, "camera_flight.png")
        )
        print("  [camera] Saved camera_ground.png + camera_flight.png")

        duration = (self._record_stop - self._record_start) if (self._record_start and self._record_stop) else 14
        real_fps = max(1, good / max(duration, 1))
        print(f"  [camera] Real framerate: {real_fps:.1f} fps ({good} frames / {duration:.1f}s)")

        outpath = os.path.join(self._output_dir, "flight_camera.mp4")
        try:
            subprocess.run([
                "ffmpeg", "-y", "-framerate", str(round(real_fps, 1)),
                "-i", os.path.join(png_dir, "frame_%04d.png"),
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-pix_fmt", "yuv420p",
                outpath
            ], capture_output=True, timeout=120)
            if os.path.exists(outpath):
                size = os.path.getsize(outpath)
                print(f"  [camera] Video: {outpath} ({size // 1024}KB)")
                shutil.rmtree(self._record_dir, ignore_errors=True)
                shutil.rmtree(png_dir, ignore_errors=True)
                return outpath
            else:
                print("  [camera] ffmpeg failed to create video")
        except Exception as e:
            print(f"  [camera] ffmpeg error: {e}")

        shutil.rmtree(self._record_dir, ignore_errors=True)
        shutil.rmtree(png_dir, ignore_errors=True)
        return None
