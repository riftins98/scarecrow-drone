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
| pixi, production shape | `pixi run webapp-prod` | builds the UI, serves it from the backend on :8000 — same shape as Docker |
| Docker (Win/Linux) | `docker compose up` | UI + API on :8000, stream on :8080 |
| venv (WSL/Windows) | `webapp/start.sh` or `Start Scarecrow.bat` | needs `.venv` |

`start.sh` supports both: it uses `CONDA_PREFIX` when set (pixi) and falls back
to `.venv`. It previously did an unconditional `source .venv/bin/activate` and
hard-failed under pixi, where no `.venv` exists.

**The backend serves the built frontend.** When `webapp/frontend/build/`
exists, `app.py` mounts it with an SPA fallback, so `:8000` is both the UI and
the API — one origin, one port, no CORS. That directory is gitignored and built
on demand (`pixi run build-frontend`, or the `webbuild` Dockerfile stage); it
used to be committed, which meant `:8000` could serve a months-old bundle with
nothing to indicate it was stale. Requests under `api/`, `detection_images/`,
`recordings/`, `mission_maps/`, `docs`, `redoc` and `openapi.json` are reserved
and still 404 rather than falling back to `index.html`.

**GUI mode is hidden where it cannot work.** `/api/sim/options` reports
`guiAvailable`, from `sim_service.gui_available()` (Linux with no
`DISPLAY`/`WAYLAND_DISPLAY` → false). In the container GUI was the preselected
option, so the customer's first click would have started a launch that could
only fail.

**The webapp does not build PX4 when a binary already exists.** `SimService`
passes `--no-build` to the launcher in that case — see
`_skip_px4_build()` in `services/sim_service.py`. Set `SCARECROW_FORCE_BUILD=1`
to opt out. Build with `pixi run build` (macOS) or `make px4_sitl_default`.

## Files
- `start.sh` — Launches backend (uvicorn) + frontend (npm start) together. Resolves pixi *or* venv.
- `Start Scarecrow.bat` — Windows launcher. Runs backend in WSL (port 8000) and frontend natively (port 3000). Waits for backend health, then opens the frontend. Pass `-d` (or `--dev`) for developer mode: keeps backend/frontend log windows visible. Normal mode writes logs to `\\wsl$\Ubuntu\tmp\scarecrow_backend.log` (WSL side, the redirect runs in bash) and `%TEMP%\scarecrow_frontend.log` (Windows side). Press any key in the launcher window to shut everything down cleanly.
