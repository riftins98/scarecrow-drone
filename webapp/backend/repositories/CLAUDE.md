# repositories

Data access layer. One repository class per database table. All SQL queries live here — nothing above this layer touches raw SQL. Takes and returns DTOs.

## Pattern
- Each repo extends `BaseRepository` for connection management
- Methods use parameterized queries (never string concat — prevents SQL injection)
- Each method opens a connection via `self._get_conn()`, executes, commits, closes in a `try/finally`
- `update()` methods whitelist allowed columns to prevent injection via kwargs

## Files
- `__init__.py` — Re-exports all repository classes for `from repositories import ...`
- `base.py` — BaseRepository with `_get_conn()` helper that calls `database.db.get_db()`
- `flight_repository.py` — FlightRepository: create/get_by_id/get_all/update/delete/end_flight/fail_flight. UUID-based TEXT ids.
- `area_map_repository.py` — AreaMapRepository: full CRUD + get_flights_for_area() for UC1
- `telemetry_repository.py` — TelemetryRepository: 1:1 with flights, keyed by flight_id
- `chase_event_repository.py` — ChaseEventRepository: create/get_by_id/get_by_flight_id/update for UC5 chase lifecycle
- `detection_image_repository.py` — DetectionImageRepository: create/get_by_flight_id for UC4 detection frames
