# webapp

Full-stack web application for flight monitoring and pigeon detection. Backend spawns flight scripts as subprocesses and monitors their stdout for detection results and telemetry.

## Subdirectories
- `backend/` — FastAPI REST API server on port 8000 (see `backend/CLAUDE.md`)
- `frontend/` — React TypeScript UI on port 3000 (see `frontend/CLAUDE.md`)
- `output/` — Generated flight videos and detection frames, organized by flight_id (gitignored)

## Running

| environment | command | notes |
|---|---|---|
| pixi (macOS) | `pixi run webapp` | backend :8000 + frontend :3000. Run `pixi run build` once first. |
| pixi, backend only | `pixi run backend` | for hitting the REST API / `/docs` directly |
| venv (WSL/Windows) | `webapp/start.sh` or `Start Scarecrow.bat` | needs `.venv` |

`start.sh` supports both: it uses `CONDA_PREFIX` when set (pixi) and falls back
to `.venv`. It previously did an unconditional `source .venv/bin/activate` and
hard-failed under pixi, where no `.venv` exists.

**The webapp does not build PX4 when a binary already exists.** `SimService`
passes `--no-build` to the launcher in that case — see
`_skip_px4_build()` in `services/sim_service.py`. Set `SCARECROW_FORCE_BUILD=1`
to opt out. Build with `pixi run build` (macOS) or `make px4_sitl_default`.

## Files
- `start.sh` — Launches backend (uvicorn) + frontend (npm start) together. Resolves pixi *or* venv.
- `Start Scarecrow Mac.sh` — macOS-specific launcher with path fixes
- `Start Scarecrow.bat` — Windows launcher. Runs backend in WSL (port 8000) and frontend natively (port 3000). Waits for backend health, then opens the frontend. Pass `-d` (or `--dev`) for developer mode: keeps backend/frontend log windows visible. Normal mode writes logs to `\\wsl$\Ubuntu\tmp\scarecrow_backend.log` (WSL side, the redirect runs in bash) and `%TEMP%\scarecrow_frontend.log` (Windows side). Press any key in the launcher window to shut everything down cleanly.
