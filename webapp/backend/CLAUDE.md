# backend

FastAPI REST API server for simulation control and flight management.

## Subdirectories
- `services/` — Business logic for simulation and detection (see `services/CLAUDE.md`)
- `database/` — SQLite database layer (see `database/CLAUDE.md`)

## Files
- `app.py` — FastAPI app with endpoints: sim connect/disconnect/status, flight start/stop, flight history, detection images
- `requirements.txt` — Python dependencies
- `scarecrow.db` — SQLite database file (gitignored)
