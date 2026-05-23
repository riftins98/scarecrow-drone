# webapp

Full-stack web application for flight monitoring and pigeon detection. Backend spawns flight scripts as subprocesses and monitors their stdout for detection results and telemetry.

## Subdirectories
- `backend/` — FastAPI REST API server on port 8000 (see `backend/CLAUDE.md`)
- `frontend/` — React TypeScript UI on port 3000 (see `frontend/CLAUDE.md`)
- `output/` — Generated flight videos and detection frames, organized by flight_id (gitignored)

## Files
- `start.sh` — Launches backend (uvicorn) + frontend (npm start) together
- `Start Scarecrow Mac.sh` — macOS-specific launcher with path fixes
- `Start Scarecrow.bat` — Windows launcher. Runs backend in WSL (port 8000) and frontend natively (port 3000). Waits for backend health, then opens the frontend. Pass `-d` (or `--dev`) for developer mode: keeps backend/frontend log windows visible. Normal mode writes logs to `\\wsl$\Ubuntu\tmp\scarecrow_backend.log` (WSL side, the redirect runs in bash) and `%TEMP%\scarecrow_frontend.log` (Windows side). Press any key in the launcher window to shut everything down cleanly.
