"""Flight lifecycle orchestration.

Coordinates FlightRepository + TelemetryRepository + DetectionService for the
full flight lifecycle: create -> start detection -> stop/abort -> summarize.
"""
import json
import os
import re
from typing import Callable, Optional

from dtos.flight_dto import FlightDTO, FlightSummaryDTO
from dtos.telemetry_dto import TelemetryCreateDTO
from repositories import (
    FlightRepository,
    TelemetryRepository,
    DetectionImageRepository,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_PURSUIT_IMAGE_RE = re.compile(
    r"leg[_-]?(\d+)[_-]pursuit[_-]?(\d+)[_-](?:attempt|attermpt)[_-]?(\d+)[_-]",
    re.IGNORECASE,
)


def _map_json_path(flight_id: str, map_path: Optional[str]) -> Optional[str]:
    candidates = []
    if map_path:
        candidates.append(os.path.join(os.path.dirname(map_path), "map.json"))
    candidates.append(os.path.join(REPO_ROOT, "webapp", "output", flight_id, "map.json"))
    for path in candidates:
        real = os.path.realpath(path)
        if os.path.isfile(real):
            return real
    return None


def _load_map_events(flight_id: str, map_path: Optional[str]) -> list[dict]:
    path = _map_json_path(flight_id, map_path)
    if not path:
        return []
    try:
        with open(path) as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    events = payload.get("events")
    return events if isinstance(events, list) else []


def _count_pursuit_flows(images) -> int:
    flows = set()
    for image in images:
        filename = os.path.basename(image.image_path)
        match = _PURSUIT_IMAGE_RE.search(filename)
        if match:
            flows.add(tuple(int(part) for part in match.groups()))
    return len(flows)


def _mission_summary_from_artifacts(
    flight_id: str,
    map_path: Optional[str],
    images,
    fallback_pigeons: int,
) -> dict:
    events = _load_map_events(flight_id, map_path)
    reached = [e for e in events if e.get("type") == "target_reached" and e.get("success", True)]
    removed = [e for e in events if e.get("type") == "target_removed" and e.get("success", True)]
    entries = [e for e in events if e.get("type") == "pursuit_entry"]

    pigeons_detected = len(entries) or len(reached) or len(removed) or fallback_pigeons
    pigeons_deterred = len(removed) if removed else len(reached)
    pursuit_flow_count = _count_pursuit_flows(images) or len(entries)

    return {
        "pigeons_detected": pigeons_detected,
        "pigeons_deterred": pigeons_deterred,
        "pursuit_flow_count": pursuit_flow_count,
    }


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
        script_name: Optional[str] = None,
        script_args: Optional[dict] = None,
    ) -> bool:
        """Start the detection subprocess for this flight.

        Args:
            flight_id: Flight identifier.
            on_detection: Callback when a detection image is parsed.
            script_name: Filename in scripts/flight/. Defaults to whatever
                DetectionService.start() considers its default
                (demo_flight_v2.py at the time of writing).
            script_args: Optional dict of CLI arg overrides.
        """
        if self.detection_service is None:
            return False
        kwargs = {"on_detection": on_detection}
        if script_name:
            kwargs["script_name"] = script_name
        if script_args is not None:
            kwargs["script_args"] = script_args
        return self.detection_service.start(flight_id, **kwargs)

    def stop_flight(self, flight_id: str) -> FlightDTO:
        """Stop detection and mark flight as completed with final counts."""
        result = {
            "pigeons_detected": 0,
            "frames_processed": 0,
            "video_path": None,
            "map_path": None,
        }
        if self.detection_service is not None:
            result = self.detection_service.stop() or result

        images = self.detection_image_repo.get_by_flight_id(flight_id)
        mission_summary = _mission_summary_from_artifacts(
            flight_id,
            result.get("map_path"),
            images,
            fallback_pigeons=result.get("pigeons_detected", 0),
        )

        self.flight_repo.end_flight(
            flight_id,
            pigeons=mission_summary["pigeons_detected"],
            frames=result.get("frames_processed", 0),
            video_path=result.get("video_path"),
            map_path=result.get("map_path"),
            pigeons_deterred=mission_summary["pigeons_deterred"],
            pursuit_flow_count=mission_summary["pursuit_flow_count"],
        )
        return self.flight_repo.get_by_id(flight_id)

    def complete_flight(
        self,
        flight_id: str,
        *,
        pigeons: int,
        frames: int,
        video_path: Optional[str] = None,
        map_path: Optional[str] = None,
    ) -> None:
        """Finalize a flight, enriching generic counters with mission artifacts."""
        images = self.detection_image_repo.get_by_flight_id(flight_id)
        mission_summary = _mission_summary_from_artifacts(
            flight_id,
            map_path,
            images,
            fallback_pigeons=pigeons,
        )
        self.flight_repo.end_flight(
            flight_id,
            pigeons=mission_summary["pigeons_detected"],
            frames=frames,
            video_path=video_path,
            map_path=map_path,
            pigeons_deterred=mission_summary["pigeons_deterred"],
            pursuit_flow_count=mission_summary["pursuit_flow_count"],
        )

    def refresh_mission_summary(self, flight_id: str, map_path: Optional[str] = None) -> None:
        """Patch mission summary fields once map/detection artifacts are available."""
        flight = self.flight_repo.get_by_id(flight_id)
        if flight is None:
            return
        images = self.detection_image_repo.get_by_flight_id(flight_id)
        mission_summary = _mission_summary_from_artifacts(
            flight_id,
            map_path or flight.map_path,
            images,
            fallback_pigeons=flight.pigeons_detected,
        )
        self.flight_repo.update(flight_id, **mission_summary)

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
