"""Manages pigeon detection subprocess."""
import json
import os
import re
import subprocess
import threading
import time
from typing import Optional, Callable

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class DetectionService:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.running = False
        self.flight_id: Optional[str] = None
        self.pigeons_detected = 0
        self.frames_processed = 0
        self.detection_images = []
        self.video_path: Optional[str] = None
        self.latest_telemetry: dict = {}
        self._on_detection: Optional[Callable] = None
        self._last_error: Optional[str] = None
        self._output_lines: list = []

    def start(self, flight_id: str, on_detection: Optional[Callable] = None) -> bool:
        """Start the detection script as a subprocess."""
        if self.running:
            return False

        self.flight_id = flight_id
        self.pigeons_detected = 0
        self.frames_processed = 0
        self.detection_images = []
        self.video_path = None
        self.latest_telemetry = {}
        self._on_detection = on_detection

        flight_script = os.path.join(REPO_ROOT, "scripts", "flight", "demo_flight_v2.py")

        # Output dir per flight
        output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
        os.makedirs(output_dir, exist_ok=True)

        env = os.environ.copy()
        env["GZ_PARTITION"] = "px4"

        self.process = subprocess.Popen(
            [
                "python3", flight_script,
                "--flight-id", flight_id,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=REPO_ROOT,
        )

        self.running = True
        t = threading.Thread(target=self._monitor, daemon=True)
        t.start()
        return True

    def _monitor(self):
        """Monitor detection subprocess stdout for protocol lines.

        Flight scripts emit these lines for webapp state:
          DETECTION_IMAGE:/path/to/img.png       -- a bird was detected
          TELEMETRY:{"battery":...,"distance":...,"detections":N}
          VIDEO_PATH:/path/to/flight_camera.mp4  -- video built after landing

        Also tolerant of older v1-style lines for backwards compat.
        """
        try:
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                self._output_lines.append(line)
                if len(self._output_lines) > 200:
                    self._output_lines = self._output_lines[-100:]

                # v2 stdout protocol
                if "DETECTION_IMAGE:" in line:
                    img_path = line.split("DETECTION_IMAGE:", 1)[-1].strip()
                    self.detection_images.append(img_path)
                    if self._on_detection:
                        self._on_detection(self.flight_id, img_path)

                elif line.startswith("TELEMETRY:"):
                    try:
                        payload = json.loads(line.split("TELEMETRY:", 1)[1].strip())
                        self.latest_telemetry = payload
                        if "detections" in payload:
                            self.pigeons_detected = int(payload["detections"])
                    except (ValueError, KeyError):
                        pass

                elif line.startswith("VIDEO_PATH:"):
                    self.video_path = line.split("VIDEO_PATH:", 1)[1].strip()

                # Shared: both v1 and v2 print "[detection] Frame N: ..."
                elif "Frame " in line:
                    match = re.search(r"Frame (\d+)", line)
                    if match:
                        self.frames_processed = max(self.frames_processed, int(match.group(1)))

                # v1 legacy summary lines
                elif "Pigeons detected:" in line:
                    match = re.search(r"Pigeons detected: (\d+)", line)
                    if match:
                        self.pigeons_detected = int(match.group(1))

                elif "Frames processed:" in line:
                    match = re.search(r"Frames processed: (\d+)", line)
                    if match:
                        self.frames_processed = int(match.group(1))

        except Exception as e:
            self._last_error = str(e)
        finally:
            self.running = False

    def stop(self) -> dict:
        """Detach from the flight process -- let it land and finish on its own.
        The flight script still needs to execute its landing sequence, build the
        video, and exit. The auto-finalize in /api/flight/status picks up the
        final state once the subprocess exits.
        """
        # Do NOT kill the process -- the flight script handles its own landing.
        self.running = False

        result = {
            "pigeons_detected": self.pigeons_detected,
            "frames_processed": self.frames_processed,
            "detection_images": list(self.detection_images),
            "video_path": self.video_path,
        }

        # Fallback: if the subprocess already built the video and printed
        # VIDEO_PATH: before the monitor got a chance to parse it, look for
        # the file on disk.
        if not result["video_path"] and self.flight_id:
            output_dir = os.path.join(REPO_ROOT, "webapp", "output", self.flight_id)
            video = os.path.join(output_dir, "flight_camera.mp4")
            if os.path.exists(video):
                result["video_path"] = video
                self.video_path = video

        return result

    @property
    def status(self) -> dict:
        return {
            "running": self.running,
            "flight_id": self.flight_id,
            "pigeons_detected": self.pigeons_detected,
            "frames_processed": self.frames_processed,
            "last_error": self._last_error,
            "log": self._output_lines[-10:],
        }
