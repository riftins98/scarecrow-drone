# webapp

Full-stack web application for flight monitoring and pigeon detection. Backend spawns flight scripts as subprocesses and monitors their stdout for detection results and telemetry.

## Subdirectories
- `backend/` — FastAPI REST API server on port 8000 (see `backend/CLAUDE.md`)
- `frontend/` — React TypeScript UI on port 3000. Components: SimControl (sim connect/disconnect, flight start/stop), FlightHistory (past flights list), FlightModal (flight detail with detection images). Pages: Dashboard. Services: api.ts. Types: flight.ts.
- `output/` — Generated flight videos and detection frames, organized by flight_id (gitignored)

## Files
- `start.sh` — Launches backend (uvicorn) + frontend (npm start) together
- `Start Scarecrow Mac.sh` — macOS-specific launcher with path fixes
- `Start Scarecrow.bat` — Windows launcher
