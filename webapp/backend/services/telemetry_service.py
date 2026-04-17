"""Telemetry tracking per flight."""
from typing import Optional

from dtos.telemetry_dto import TelemetryCreateDTO, TelemetryDTO
from repositories import TelemetryRepository


class TelemetryService:
    def __init__(self, telemetry_repo: Optional[TelemetryRepository] = None):
        self.telemetry_repo = telemetry_repo or TelemetryRepository()

    def init_telemetry(self, flight_id: str) -> TelemetryDTO:
        """Create a telemetry row for a new flight. Idempotent if already exists."""
        existing = self.telemetry_repo.get_by_flight_id(flight_id)
        if existing is not None:
            return existing
        return self.telemetry_repo.create(TelemetryCreateDTO(flight_id=flight_id))

    def update_telemetry(
        self,
        flight_id: str,
        battery_level: Optional[float] = None,
        distance: Optional[float] = None,
        detections: Optional[int] = None,
    ) -> None:
        updates = {}
        if battery_level is not None:
            updates["battery_level"] = battery_level
        if distance is not None:
            updates["distance"] = distance
        if detections is not None:
            updates["detections"] = detections
        if updates:
            self.telemetry_repo.update(flight_id, **updates)

    def get_telemetry(self, flight_id: str) -> Optional[TelemetryDTO]:
        return self.telemetry_repo.get_by_flight_id(flight_id)
