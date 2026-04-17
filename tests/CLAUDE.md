# tests

Pytest test suite. Runs via `pytest` from project root (config in `pyproject.toml`).

## Testing Philosophy

This project has three distinct testing layers because "100% automated coverage" isn't feasible for drone/subprocess code.

### Layer 1: Unit tests (automated, fast)
**Scope**: Pure computation — controllers, algorithms, repositories, services, DTOs.
**Mocked**: External dependencies (MAVSDK, YOLO, Gazebo subprocesses).
**DB**: In-memory SQLite via `repo_db` fixture.
**Speed**: Under 2 seconds for full suite.
**Coverage target**: 90%+ of the code in this layer.

### Layer 2: Integration tests (automated, fast)
**Scope**: Full HTTP request → Controller → Service → Repository → DB flow.
**Tool**: FastAPI TestClient via `httpx.AsyncClient`.
**Mocked**: Subprocess spawning (SimService.launch, DetectionService.start). The services themselves run real code; only the `subprocess.Popen` call is stubbed.
**DB**: In-memory SQLite, fully populated via migrations.
**Speed**: Under 5 seconds.
**Coverage target**: 100% of controller routes and service orchestration logic.

### Layer 3: Manual sim verification (human, slow)
**Scope**: Actual drone behavior in Gazebo — takeoff, wall-following, detection, landing.
**Not automated** because:
- Gazebo startup: 30-60s per test
- Flaky (world loading, race conditions, GUI)
- Can't run on CI without GPU/display
- Real flight crashes require recovery
See `docs/implementation/MANUAL_SIM_CHECKLIST.md` for the verification checklist used after drone code changes.

### What NOT to try to automate
These are intentionally left at low unit-test coverage:
- `webapp/backend/services/sim_service.py` — spawns PX4 process
- `webapp/backend/services/detection_service.py` — spawns flight script, parses stdout
- `scarecrow/sensors/lidar/gazebo.py`, `scarecrow/sensors/camera/gazebo.py` — require Gazebo running
- `scarecrow/flight/helpers.py`, `scarecrow/flight/stabilization.py` — require MAVSDK connection
- `scarecrow/controllers/rotation.py` (async parts) — require MAVSDK drone

Coverage numbers here mean "code we trust because we run it in sim manually," not "untested code."

## Running

```bash
pytest                                         # all tests
pytest tests/unit/                              # unit only
pytest tests/integration/                       # integration only
pytest tests/unit/test_wall_follow.py -v        # specific file
pytest -k "test_create"                         # by name pattern
pytest --cov=webapp/backend --cov=scarecrow     # with coverage report
```

## Files
- `conftest.py` — Shared fixtures for unit tests: `in_memory_db` (raw connection), `repo_db` (patches `get_db()`), `mock_lidar_scan` (LidarScan factory).
- `__init__.py` — Empty, makes tests a package.

## Subdirectories
- `unit/` — Test files organized by source package to mirror the codebase:
  - `unit/scarecrow/controllers/` — WallFollow, DistanceStabilizer, FrontWallDetector
  - `unit/scarecrow/sensors/` — LidarScan, GazeboLidar topic discovery, gz_utils prefetch
  - `unit/scarecrow/detection/` — YoloDetector (rate limiting, callback, preload_async)
  - `unit/scarecrow/navigation/` — NavigationUnit, MapUnit
  - `unit/scarecrow/flight/` — Flight orchestrator
  - `unit/scarecrow/drone/` — Drone class (with mocked mavsdk.System)
  - `unit/webapp/repositories/` — all 5 repository classes (UT-12..15 + DetectionImage)
  - `unit/webapp/services/` — all 6 business services
- `integration/` — One file per controller + flow tests (flight lifecycle, chase, area map, drone, detection, connection, sim, static, health). Covers full HTTP stack with mocked subprocesses.

## Key Fixture Detail (repo_db)
`repo_db` wraps the SQLite connection in `_NonClosingConn` so repository code (which calls `conn.close()` after each query) doesn't tear down the test's shared connection between repo calls. The real connection closes at test teardown.
