# database

SQLite persistence layer for flight history, detection results, area maps, telemetry, and chase events. Database file: `scarecrow.db` (gitignored, auto-created on first import).

## Files
- `db.py` — Database init and CRUD functions. `init_db()` runs pending migrations on import. `get_db()` returns a connection with Row factory. Functions: `create_flight()` (UUID-based TEXT id), `end_flight()`, `fail_flight()`, `add_detection_image()`, `get_flights()`, `get_flight()`, `get_flight_images()`. Phase 1 moves these into repository classes.
- `migrate.py` — Idempotent migration runner. Discovers files in `migrations/`, tracks applied ones in `_migrations` table, runs pending ones in sorted order. Safe to run repeatedly on both empty and existing databases.

## Subdirectories
- `migrations/` — Numbered migration files (`NNN_description.py`). Each exports an `up(conn)` function. Run in sorted filename order.

## Current Schema (6 tables)
- `flights` — id TEXT PK, area_map_id FK (nullable), start_time, end_time, duration, pigeons_detected, frames_processed, status, video_path
- `detection_images` — id INTEGER PK, flight_id FK, image_path, timestamp
- `area_maps` — id INTEGER PK, name, created_at, updated_at, boundaries (JSON), area_size, status (UC1)
- `telemetry` — flight_id PK/FK, battery_level, distance, detections (per-flight totals)
- `chase_events` — id INTEGER PK, flight_id FK, detection_image_id FK (nullable), start_time, end_time, counter_measure_type, outcome (UC5)
- `_migrations` — name PK, applied_at (migration tracking, internal)

## Adding a Migration
Create `migrations/NNN_description.py` with an `up(conn)` function. Use `CREATE TABLE IF NOT EXISTS` for tables, and `PRAGMA table_info()` checks before `ALTER TABLE ADD COLUMN` for column additions. Never DROP tables or columns in a migration — only add/modify.
