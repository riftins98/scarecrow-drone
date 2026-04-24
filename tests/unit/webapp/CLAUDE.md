# webapp (unit tests)

Unit tests for `webapp/backend/`. Services and repositories only — controllers live in `tests/integration/` because they need the FastAPI stack.

## Subdirectories
- `repositories/` — All 5 repository classes against in-memory SQLite.
- `services/` — Business services (flight, drone, area_map, chase, telemetry, recording). Subprocess services (sim, detection) are intentionally skipped — see root `tests/CLAUDE.md`.

## Files
- `__init__.py` — Package marker (empty).
