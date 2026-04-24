# migrations

Numbered SQLite migrations. Each file exports `up(conn)` and is run once by `migrate.py` in sorted filename order; applied names are tracked in the `_migrations` table.

## Files
- `__init__.py` — Package marker (empty).
- `001_initial_tables.py` — Creates `flights` and `detection_images`.
- `002_add_area_maps.py` — Creates `area_maps` for UC1 Map Area.
- `003_add_telemetry.py` — Creates `telemetry` (1:1 with flights).
- `004_add_chase_events.py` — Creates `chase_events` for UC5.
- `005_flights_add_area_map_id.py` — Adds `area_map_id` FK column to `flights` via `ALTER TABLE ADD COLUMN`.

## Rules
- Never DROP a table or column in a migration — only add/modify.
- Use `CREATE TABLE IF NOT EXISTS` and guard `ALTER TABLE ADD COLUMN` with `PRAGMA table_info()` checks so migrations remain idempotent.
