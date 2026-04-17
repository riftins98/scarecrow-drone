# backend

FastAPI REST API server. Fully layered architecture: Controllers -> Services -> Repositories -> DTOs -> Database. 40 API routes organized by domain.

## Subdirectories
- `controllers/` — FastAPI router modules, one per ADD Appendix A section (see `controllers/CLAUDE.md`)
- `services/` — Business logic: flight, drone, area_map, chase, telemetry, recording + legacy sim/detection (see `services/CLAUDE.md`)
- `repositories/` — Data access layer, one class per table (see `repositories/CLAUDE.md`)
- `dtos/` — Pydantic data transfer objects for all entities (see `dtos/CLAUDE.md`)
- `database/` — SQLite migrations and connection layer (see `database/CLAUDE.md`)

## Files
- `app.py` — FastAPI app entry point. Slim — just creates the app, adds CORS middleware, includes all router modules, defines `/api/health`. Run with `uvicorn app:app --port 8000`.
- `dependencies.py` — Shared service singletons. All controllers import from here so state (running subprocess, telemetry cache) is consistent across routes. One instance per process.
- `requirements.txt` — Production webapp deps (fastapi, uvicorn, aiofiles, pydantic).

## Architecture Flow
```
HTTP Request
  -> controllers/xxx_controller.py    (route handler, Pydantic validation)
     -> services/xxx_service.py       (business logic)
        -> repositories/xxx_repository.py  (SQL via DTOs)
           -> database/db.py + SQLite
```

## API Endpoint Coverage (40 routes)
- `/api/health` — health check
- `/api/sim/*` — A.1 simulation lifecycle (3 routes)
- `/api/connection/*` — A.2 connection status (6 routes, mocked for sim)
- `/api/drone/*` — A.3 drone control (6 routes)
- `/api/flights/*`, `/api/flight/*` — A.4 flight history (9 routes + 3 legacy)
- `/api/areas/*` — A.5 area maps (8 routes)
- `/api/detection/*` — A.6 detection config (3 routes)
- `/api/flights/{id}/chases`, `/api/chases/{id}` — A.7 chase events (2 routes)
- `/detection_images/*`, `/recordings/*` — static file serving

See `controllers/CLAUDE.md` for per-controller details.

## Running
```bash
# Dev server
uvicorn app:app --port 8000 --reload

# OpenAPI docs
http://localhost:8000/docs
```