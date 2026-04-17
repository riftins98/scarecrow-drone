"""Flight lifecycle orchestration.

Coordinates FlightRepository + TelemetryRepository + DetectionService for the
full flight lifecycle: create -> start detection -> stop/abort -> summarize.
"""
from typing import Callable, Optional

from dtos.flight_dto import FlightDTO, FlightSummaryDTO
from dtos.telemetry_dto import TelemetryCreateDTO
from repositories import (
    FlightRepository,
    TelemetryRepository,
    DetectionImageRepository,
)


class FlightService:
    def __init__(
        self,
        flight_repo: Optional[FlightRepository] = None,
        telemetry_repo: Optional[TelemetryRepository] = None,
        detection_image_repo: Optional[DetectionImageRepository] = None,
        detection_service=None,
    ):
        self.flight_repo = flight_repo or FlightRepository()
        self.telemetry_repo = telemetry_repo or TelemetryRepository()
        self.detection_image_repo = detection_image_repo or DetectionImageRepository()
        self.detection_service = detection_service

    def create_flight(self, area_map_id: Optional[int] = None) -> FlightDTO:
        """Create a flight record and initialize its telemetry row."""
        flight = self.flight_repo.create(area_map_id=area_map_id)
        self.telemetry_repo.create(TelemetryCreateDTO(flight_id=flight.id))
        return flight

    def start_detection(
        self,
        flight_id: str,
        on_detection: Optional[Callable] = None,
    ) -> bool:
        """Start the detection subprocess for this flight."""
        if self.detection_service is None:
            return False
        return self.detection_service.start(flight_id, on_detection=on_detection)

    def stop_flight(self, flight_id: str) -> FlightDTO:
        """Stop detection and mark flight as completed with final counts."""
        result = {"pigeons_detected": 0, "frames_processed": 0, "video_path": None}
        if self.detection_service is not None:
            result = self.detection_service.stop() or result

        self.flight_repo.end_flight(
            flight_id,
            pigeons=result.get("pigeons_detected", 0),
            frames=result.get("frames_processed", 0),
            video_path=result.get("video_path"),
        )
        return self.flight_repo.get_by_id(flight_id)

    def abort_flight(self, flight_id: str) -> Optional[FlightDTO]:
        """Mark flight aborted. Assumes DroneService already stopped the subprocess."""
        flight = self.flight_repo.get_by_id(flight_id)
        if flight is None or flight.status != "in_progress":
            return flight
        from datetime import datetime
        self.flight_repo.update(
            flight_id,
            status="aborted",
            end_time=datetime.now().isoformat(),
        )
        return self.flight_repo.get_by_id(flight_id)

    def get_flight(self, flight_id: str) -> Optional[FlightDTO]:
        return self.flight_repo.get_by_id(flight_id)

    def get_all_flights(self) -> list[FlightDTO]:
        return self.flight_repo.get_all()

    def get_flight_summary(self, flight_id: str) -> Optional[FlightSummaryDTO]:
        flight = self.flight_repo.get_by_id(flight_id)
        if flight is None:
            return None
        images = self.detection_image_repo.get_by_flight_id(flight_id)
        return FlightSummaryDTO(
            flight_id=flight.id,
            duration=flight.duration,
            total_detections=len(images),
        )

    def delete_flight(self, flight_id: str) -> bool:
        return self.flight_repo.delete(flight_id)
