# backend

FastAPI REST API server. Fully layered architecture: Controllers -> Services -> Repositories -> DTOs -> Database. 50 routes under `/api`, plus three static mounts and the SPA fallback.

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

## API Endpoint Coverage

Counts are method-level (a path with GET and DELETE is two). Regenerate with
`python -c "from app import app; print(sum(len(r.methods-{'HEAD','OPTIONS'}) for r in app.routes if getattr(r,'methods',None)))"`.

| prefix | routes | ADD section |
|---|---|---|
| `/api/sim/*` | 11 | A.1 simulation lifecycle (connect, disconnect, status, options, cameras, camera, spawn, reset, log, log/view, log/stream) |
| `/api/flights/*` | 8 | A.4 flight history |
| `/api/areas/*` | 8 | A.5 area maps |
| `/api/flight/*` | 6 | A.4 legacy single-flight aliases |
| `/api/drone/*` | 6 | A.3 drone control |
| `/api/connection/*` | 6 | A.2 connection status (mocked for sim) |
| `/api/detection/*` | 3 | A.6 detection config |
| `/api/chases/*` | 1 | A.7 chase events |
| `/api/health` | 1 | — |
| `/detection_images/*`, `/recordings/*`, `/mission_maps/*` | 3 | static file serving |
| `/{full_path:path}` | 1 | SPA fallback to `index.html` |

See `controllers/CLAUDE.md` for per-controller details.

## Running
```bash
# Dev server
uvicorn app:app --port 8000 --reload

# OpenAPI docs
http://localhost:8000/docs
```
