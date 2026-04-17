# controllers

FastAPI router modules. One controller per ADD Appendix A section. Each module exports a `router` that `app.py` includes. Controllers are thin — they validate requests, call services, format responses.

## Pattern
- Each file has `router = APIRouter(prefix="/api/xxx", tags=["xxx"])`
- Services imported from `dependencies.py` (shared singletons, NOT instantiated per-request)
- Pydantic request models defined inline for endpoints that take JSON bodies
- 404 for missing resources, 400 for bad state, 500 for server errors

## Files
- `__init__.py` — Re-exports all controller modules for `from controllers import *`
- `sim_controller.py` — `/api/sim/*` (ADD A.1): connect, disconnect, status
- `flight_controller.py` — `/api/flights/*` (ADD A.4) + legacy `/api/flight/start|stop|status`. The legacy routes stay for frontend compatibility until the React side is updated.
- `drone_controller.py` — `/api/drone/*` (ADD A.3): start, stop, abort, return-home, status, telemetry. Frontend-facing drone control.
- `area_map_controller.py` — `/api/areas/*` (ADD A.5): full CRUD + `/mapping/start` and `/mapping/status` for UC1
- `detection_controller.py` — `/api/detection/*` (ADD A.6): status, config GET/PUT (confidence threshold)
- `chase_event_controller.py` — `/api/flights/{id}/chases` and `/api/chases/{id}` (ADD A.7) for UC5
- `connection_controller.py` — `/api/connection/*` (ADD A.2): wifi/ssh return mock responses during simulation phase, will talk to Raspberry Pi when hardware arrives
- `static_controller.py` — Non-`/api/` file serving: `/detection_images/{flight_id}/{filename}` and `/recordings/{flight_id}/{filename}`. Uses `_safe_path()` to block path traversal attacks.

## Adding a new route
1. Find the right controller by domain (or add new controller module + register in app.py + `__init__.py`)
2. Import services from `dependencies.py` (not from `services/`) so state is shared
3. Add integration test in `tests/integration/test_xxx_api.py`
4. Update this CLAUDE.md's file list if adding a new controller module