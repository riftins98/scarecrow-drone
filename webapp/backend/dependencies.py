"""Shared service singletons used by all controllers.

One instance of each service per process. Controllers import from here rather
than instantiating their own so state (active subprocess, telemetry cache) is
consistent across routes.
"""
from services import (
    SimService,
    DetectionService,
    FlightService,
    DroneService,
    AreaMapService,
    ChaseEventService,
    TelemetryService,
    RecordingService,
)

sim_service = SimService()
detection_service = DetectionService()
telemetry_service = TelemetryService()
chase_event_service = ChaseEventService()
area_map_service = AreaMapService()
recording_service = RecordingService()

flight_service = FlightService(detection_service=detection_service)
drone_service = DroneService(detection_service=detection_service)
