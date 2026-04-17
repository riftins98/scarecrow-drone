"""Drone subprocess state wrapper.

Today: thin wrapper around DetectionService for flight lifecycle commands.
Phase 3-6 (UC7 Abort, UC5 Chase) extend this with SIGTERM handling and
telemetry stdout parsing.
"""
from typing import Optional


class DroneService:
    def __init__(self, detection_service=None):
        self.detection_service = detection_service
        self._latest_telemetry: dict = {}
        self._current_flight_id: Optional[str] = None

    @property
    def current_flight_id(self) -> Optional[str]:
        if self.detection_service is not None:
            return self.detection_service.flight_id
        return self._current_flight_id

    def get_status(self) -> dict:
        """Drone operational status for `/api/drone/status`."""
        is_connected = False
        is_flying = False
        if self.detection_service is not None:
            is_flying = self.detection_service.running
        return {
            "isConnected": is_connected,
            "isFlying": is_flying,
            "mode": "offboard" if is_flying else "idle",
            "batteryLevel": self._latest_telemetry.get("battery"),
        }

    def start_flight(self, flight_id: str, on_detection=None) -> bool:
        """Spawn the detection flight subprocess."""
        if self.detection_service is None:
            return False
        return self.detection_service.start(flight_id, on_detection=on_detection)

    def stop_flight(self) -> dict:
        """Gracefully stop the flight subprocess (lets it land)."""
        if self.detection_service is None:
            return {}
        return self.detection_service.stop() or {}

    def abort(self) -> bool:
        """Emergency abort. Stub: Phase 6 (UC7) implements SIGTERM + emergency landing."""
        if self.detection_service is None:
            return False
        self.detection_service.stop()
        return True

    def return_home(self) -> bool:
        """Command return-to-home. Stub: Phase 6 implements RTL via MAVSDK."""
        return self.abort()

    def get_telemetry(self) -> dict:
        return dict(self._latest_telemetry)

    def update_telemetry(self, data: dict) -> None:
        """Called by subprocess stdout parser when a TELEMETRY: line arrives."""
        self._latest_telemetry = data
