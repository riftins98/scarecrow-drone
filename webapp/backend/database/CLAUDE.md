# database

SQLite persistence layer for flight history and detection results. Database file: `scarecrow.db` (gitignored, auto-created on first import).

## Files
- `db.py` — Database init and CRUD functions. `init_db()` creates tables on import. `get_db()` returns a connection with Row factory. Functions: `create_flight()` (UUID-based TEXT id), `end_flight()`, `fail_flight()`, `add_detection_image()`, `get_flights()`, `get_flight()`, `get_flight_images()`. Phase 1 moves these into repository classes.

## Current Schema (2 tables)
- `flights` — id TEXT PK, start_time, end_time, duration, pigeons_detected, frames_processed, status, video_path
- `detection_images` — id INTEGER PK, flight_id FK, image_path, timestamp

## Missing Tables (added in Phase 0)
- `area_maps` — for UC1 Map Area
- `telemetry` — for flight telemetry tracking
- `chase_events` — for UC5 Chase Birds
