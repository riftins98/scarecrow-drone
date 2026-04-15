# backend

FastAPI REST API server for simulation control and flight management. Currently a flat architecture (all routes in app.py). Phase 1 of the implementation plan restructures this into Controllers -> Services -> Repositories -> DTOs.

## Subdirectories
- `services/` — Business logic: SimService (PX4+Gazebo lifecycle), DetectionService (flight subprocess management) (see `services/CLAUDE.md`)
- `database/` — SQLite database layer: schema init, CRUD functions (see `database/CLAUDE.md`)

## Files
- `app.py` — FastAPI app with ALL endpoints inline (12 routes): sim connect/disconnect/status, flight start/stop/status, flight history CRUD, detection image serving, video recording serving, health check. This monolith will be split into controller modules in Phase 1.
- `requirements.txt` — Python dependencies (fastapi, uvicorn, python-multipart)

## Current API Endpoints (all in app.py)
- `POST/DELETE /api/sim/connect`, `GET /api/sim/status` — simulation lifecycle
- `POST /api/flight/start`, `POST /api/flight/stop`, `GET /api/flight/status` — detection session
- `GET /api/flights`, `GET /api/flights/{id}`, `GET /api/flights/{id}/images`, `GET /api/flights/{id}/recording` — flight history
- `GET /api/health` — health check
