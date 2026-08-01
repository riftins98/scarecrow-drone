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
from ..gz_transport import GzSubscription, transport_available
from ..gz_utils import get_gz_env


def frame_from_proto(msg) -> np.ndarray | None:
    """Convert a gz.msgs Image into a BGR numpy array.

    The subscription path gets the pixels as a bytes field, so none of the
    text-format unescaping below applies -- that whole dance exists only
    because the CLI prints the image inside a quoted protobuf-text string.

    Returns BGR to match parse_gz_frame: every consumer (YOLO, the recorder,
    the streamer) already expects BGR, and getting it backwards is silent --
    the picture still looks like a picture, detection accuracy just drops.
    """
    try:
        width = int(msg.width)
        height = int(msg.height)
        raw = msg.data
    except Exception:
        return None

    if width <= 0 or height <= 0:
        return None
    expected = width * height * 3
    if raw is None or len(raw) < expected:
        return None

    try:
        pixels = np.frombuffer(raw[:expected], dtype=np.uint8).reshape(
            (height, width, 3)
        )
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    except Exception:
        return None


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
        self._subscription: GzSubscription | None = None
        self.on_frame = None   # callback(frame: np.ndarray) — set before start()

        # Recording state
        self._recording = False
        self._record_dir: str | None = None
        self._output_dir: str | None = None
        self._frame_count = 0
        self._record_start: float | None = None
        self._record_stop: float | None = None

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
            raise RuntimeError("Could not find camera topic in Gazebo")
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
            from gz.msgs10.image_pb2 import Image
        except Exception:
            return False
        sub = GzSubscription(self._topic, Image, self._on_image, env=self._env)
        if not sub.start():
            return False
        self._subscription = sub
        return True

    def _on_image(self, msg) -> None:
        image = frame_from_proto(msg)
        if image is not None:
            self._publish(image)

    def _publish(self, image) -> None:
        """Store, optionally record, and hand the frame to the consumer.

        Shared by both read paths so recording and the on_frame contract cannot
        drift apart depending on how the frame arrived.

        Recording writes a decoded PNG rather than the raw dump it used to.
        The dump only ever existed because the CLI hands back protobuf *text*,
        which had to be unescaped later; the subscription has no such format to
        preserve, and save_video was decoding straight to PNG anyway. Writing
        the PNG now does that work once instead of twice.
        """
        with self._lock:
            self._latest_frame = CameraFrame(image=image)

        if self._recording and self._record_dir:
            with self._lock:
                n = self._frame_count
                self._frame_count += 1
            try:
                cv2.imwrite(
                    os.path.join(self._record_dir, f"frame_{n:04d}.png"), image
                )
            except Exception:
                pass

        if self.on_frame is not None:
            self.on_frame(image)

    def stop(self) -> None:
        self._running = False
        self._recording = False
        if self._subscription is not None:
            self._subscription.stop()
            self._subscription = None
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

                self._publish(image)

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

        # Frames are recorded as decoded PNGs. The raw_*.bin branch stays for
        # recordings made before that change, and for anything that still feeds
        # this method CLI dumps.
        captured = sorted(glob.glob(os.path.join(self._record_dir, "frame_*.png")))
        raw_files = sorted(glob.glob(os.path.join(self._record_dir, "raw_*.bin")))
        if not captured and not raw_files:
            print("  [camera] No frames captured")
            return None

        png_dir = os.path.join(self._output_dir, ".camera_png")
        os.makedirs(png_dir, exist_ok=True)
        good = 0

        # ffmpeg needs a gap-free frame_%04d sequence, so renumber rather than
        # copying names through: a single unreadable frame would otherwise end
        # the video early at the hole.
        for pngfile in captured:
            try:
                frame = cv2.imread(pngfile)
                if frame is not None:
                    cv2.imwrite(os.path.join(png_dir, f"frame_{good:04d}.png"), frame)
                    good += 1
            except Exception:
                pass

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

        print(f"  [camera] Decoded {good}/{len(captured) + len(raw_files)} frames")

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
