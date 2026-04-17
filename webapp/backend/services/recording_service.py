"""Video recording lifecycle for UC3 (Record Flight Video).

Today: tracks recording status from flight subprocess output. The actual
recording logic (PNG capture + ffmpeg stitching) lives in the flight script
via GazeboCamera.start_recording/stop_recording/save_video. This service
just exposes status to the webapp.
"""
from typing import Optional


class RecordingService:
    def __init__(self):
        self._recording = False
        self._flight_id: Optional[str] = None
        self._video_path: Optional[str] = None

    def on_flight_started(self, flight_id: str) -> None:
        """Called when a detection flight subprocess spawns."""
        self._recording = True
        self._flight_id = flight_id
        self._video_path = None

    def on_video_ready(self, video_path: str) -> None:
        """Called when the flight subprocess reports VIDEO_PATH: or finishes."""
        self._recording = False
        self._video_path = video_path

    def on_flight_ended(self) -> None:
        self._recording = False

    def get_status(self) -> dict:
        return {
            "recording": self._recording,
            "flightId": self._flight_id,
            "videoPath": self._video_path,
        }
