# repositories (unit tests)

Tests for each `webapp/backend/repositories/` class. Uses the shared `repo_db` fixture (in-memory SQLite with `_NonClosingConn` wrapper) so repository `conn.close()` calls don't tear down the test connection.

## Files
- `__init__.py` — Package marker (empty).
- `test_flight_repository.py` — FlightRepository CRUD + end_flight/fail_flight.
- `test_area_map_repository.py` — AreaMapRepository CRUD + get_flights_for_area.
- `test_telemetry_repository.py` — TelemetryRepository 1:1 with flights.
- `test_chase_event_repository.py` — ChaseEventRepository create/get/update for UC5.
- `test_detection_image_repository.py` — DetectionImageRepository create + get_by_flight_id.
