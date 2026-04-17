# backend

FastAPI REST API server for simulation control and flight management. Mid-refactor into layered architecture: Controllers -> Services -> Repositories -> DTOs. DTOs and repositories are complete; app.py still holds all routes (Phase 1d will split into controllers).

## Subdirectories
- `dtos/` — Pydantic data transfer objects for all entities (see `dtos/CLAUDE.md`)
- `repositories/` — Data access layer, one class per table (see `repositories/CLAUDE.md`)
- `services/` — Business logic: SimService, DetectionService (see `services/CLAUDE.md`). More services added in Phase 1c.
- `database/` — SQLite migrations and connection layer (see `database/CLAUDE.md`)

## Files
- `app.py` — FastAPI app with ALL endpoints inline (12 routes): sim connect/disconnect/status, flight start/stop/status, flight history CRUD, detection image serving, video recording serving, health check. Will be split into controller modules in Phase 1d.
- `requirements.txt` — Python dependencies (fastapi, uvicorn, aiofiles)

## Current API Endpoints (all in app.py)
- `POST/DELETE /api/sim/connect`, `GET /api/sim/status` — simulation lifecycle
- `POST /api/flight/start`, `POST /api/flight/stop`, `GET /api/flight/status` — detection session
- `GET /api/flights`, `GET /api/flights/{id}`, `GET /api/flights/{id}/images`, `GET /api/flights/{id}/recording` — flight history
- `GET /api/health` — health check
