"""Manages pigeon detection subprocess."""
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
        self._on_detection = on_detection

        detect_script = os.path.join(REPO_ROOT, "scripts", "flight", "detect_pigeons.py")
        model_path = os.path.join(REPO_ROOT, "models", "yolo", "best_v4.pt")

        # Output dir per flight
        output_dir = os.path.join(REPO_ROOT, "webapp", "output", flight_id)
        os.makedirs(output_dir, exist_ok=True)

        env = os.environ.copy()
        env["GZ_PARTITION"] = "px4"
        try:
            result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=3)
            ip = result.stdout.strip().split()[0]
            if ip:
                env["GZ_IP"] = ip
        except Exception:
            pass

        # Override output dir in detection script via env
        env["DETECTION_OUTPUT_DIR"] = output_dir

        self.process = subprocess.Popen(
            [
                "python3", detect_script,
                "--model", model_path,
                "--confidence", "0.3",
                "--duration", "0",  # unlimited
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
        """Monitor detection output and parse results."""
        try:
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                self._output_lines.append(line)
                if len(self._output_lines) > 200:
                    self._output_lines = self._output_lines[-100:]

                # Parse detection lines
                if "pigeon(s) detected" in line:
                    # e.g. "  [  48.6s] Frame 5: 1 pigeon(s) detected!"
                    match = re.search(r"Frame (\d+): (\d+) pigeon", line)
                    if match:
                        self.frames_processed = int(match.group(1))
                        self.pigeons_detected += int(match.group(2))

                elif "no detections" in line:
                    match = re.search(r"Frame (\d+):", line)
                    if match:
                        self.frames_processed = int(match.group(1))

                elif "DETECTION_IMAGE:" in line:
                    # Custom output from detect_pigeons.py
                    img_path = line.split("DETECTION_IMAGE:")[-1].strip()
                    self.detection_images.append(img_path)
                    if self._on_detection:
                        self._on_detection(self.flight_id, img_path)

                elif "Frames processed:" in line:
                    match = re.search(r"Frames processed: (\d+)", line)
                    if match:
                        self.frames_processed = int(match.group(1))

                elif "Total pigeons detected:" in line:
                    match = re.search(r"Total pigeons detected: (\d+)", line)
                    if match:
                        self.pigeons_detected = int(match.group(1))

        except Exception as e:
            self._last_error = str(e)
        finally:
            self.running = False

    def stop(self) -> dict:
        """Stop detection and return results."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

        self.running = False
        result = {
            "pigeons_detected": self.pigeons_detected,
            "frames_processed": self.frames_processed,
            "detection_images": self.detection_images,
        }

        # Find video if created
        if self.flight_id:
            output_dir = os.path.join(REPO_ROOT, "webapp", "output", self.flight_id)
            video = os.path.join(output_dir, "flight_camera.mp4")
            if os.path.exists(video):
                result["video_path"] = video

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
