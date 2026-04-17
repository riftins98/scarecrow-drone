# services

Business logic layer. Services coordinate repositories and external resources (subprocesses). Two categories of service live here:

- **Subprocess services** (sim_service, detection_service): manage long-running external processes. Stateful — hold PID, running flag, parsed stdout. Not easily unit-tested.
- **Business services** (flight, drone, area_map, chase_event, telemetry, recording): pure orchestration over repositories. Fully unit-testable.

## Files
- `__init__.py` — Re-exports all services for `from services import *`
- `sim_service.py` — `SimService`: manages PX4+Gazebo lifecycle. `launch()` spawns PX4 SITL build as subprocess, tracks 11-stage launch progress (clean, copy models, build, launch, etc.), `stop()` kills process tree.
- `detection_service.py` — `DetectionService`: spawns `scripts/flight/demo_flight.py` as subprocess with `--flight-id`. Background thread monitors stdout, parses `DETECTION_IMAGE:` lines for image paths. `stop()` detaches rather than kills (flight script handles its own landing).
- `flight_service.py` — `FlightService`: flight lifecycle (create_flight, start_detection, stop_flight, abort_flight, get_flight_summary, delete_flight). Coordinates FlightRepository + TelemetryRepository + DetectionService.
- `drone_service.py` — `DroneService`: wraps DetectionService with drone-specific API (get_status, start_flight, stop_flight, abort, return_home, get_telemetry). Phase 6 (UC7) will extend with SIGTERM handling.
- `area_map_service.py` — `AreaMapService`: CRUD for area maps + mapping session state (start_mapping is stubbed for Phase 3 UC1).
- `chase_event_service.py` — `ChaseEventService`: chase event lifecycle for UC5. Validates counter_measure_type (pursuit/movement/combined) and outcome (dispersed/lost/aborted).
- `telemetry_service.py` — `TelemetryService`: per-flight telemetry tracking (battery, distance, detection count). 1:1 with flights.
- `recording_service.py` — `RecordingService`: video recording status for UC3. The actual PNG+ffmpeg pipeline lives in GazeboCamera; this service just tracks recording state for the webapp.

## Subprocess stdout protocol
Flight scripts communicate with services via stdout lines parsed by the monitoring thread:
- `DETECTION_IMAGE:/path/to/img.png` — parsed by DetectionService (implemented)
- Future (Phase 4-6): `TELEMETRY:{json}`, `CHASE_START:type`, `CHASE_END:outcome`, `MAP_RESULT:{json}`, `ABORT_REQUESTED`
