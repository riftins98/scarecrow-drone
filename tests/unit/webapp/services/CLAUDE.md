# services (unit tests)

Tests for the business-logic services in `webapp/backend/services/`. Subprocess services (SimService, DetectionService) are NOT covered here — see root `tests/CLAUDE.md` for the rationale.

## Files
- `__init__.py` — Package marker (empty).
- `test_flight_service.py` — Flight lifecycle orchestration over FlightRepository + TelemetryRepository + DetectionService.
- `test_drone_service.py` — DroneService thin wrapper over DetectionService.
- `test_area_map_service.py` — AreaMapService CRUD + start_mapping stub.
- `test_chase_event_service.py` — ChaseEventService lifecycle + counter_measure_type/outcome validation.
- `test_telemetry_service.py` — Per-flight telemetry updates.
- `test_recording_service.py` — Recording-state tracking for UC3.
