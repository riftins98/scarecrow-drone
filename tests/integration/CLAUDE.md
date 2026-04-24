# integration

FastAPI integration tests. Each file exercises a controller via `httpx.AsyncClient` against an in-memory SQLite DB. Subprocess spawning (Sim/Detection services) is stubbed at the `subprocess.Popen` boundary; everything else runs real code.

## Files
- `__init__.py` — Package marker (empty).
- `conftest.py` — Fixtures: app instance with migrations applied against in-memory DB, async test client, subprocess stubs.
- `test_health.py` — `/api/health`.
- `test_sim_api.py` — `/api/sim/*` (A.1 simulation lifecycle).
- `test_connection_api.py` — `/api/connection/*` (A.2 mocked responses).
- `test_drone_api.py` — `/api/drone/*` (A.3 drone control).
- `test_flight_api.py` — `/api/flights/*` + legacy `/api/flight/*` (A.4 history).
- `test_area_map_api.py` — `/api/areas/*` (A.5 UC1 Map Area).
- `test_detection_api.py` — `/api/detection/*` (A.6).
- `test_chase_api.py` — `/api/flights/{id}/chases` (A.7 UC5).
- `test_static_api.py` — `/detection_images/*` and `/recordings/*` static serving, including path-traversal guards.
- `test_flight_lifecycle.py` — End-to-end flow: create flight → start detection → telemetry updates → stop → summary.
