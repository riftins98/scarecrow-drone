# tests

Pytest test suite. Runs via `pytest` from project root (config in `pyproject.toml`). Test files mirror source structure in `tests/unit/`.

## Strategy
- **Unit tests** (`tests/unit/`): Test individual classes in isolation. DB tests use in-memory SQLite via `repo_db` fixture (NOT the real `scarecrow.db` file). External services (MAVSDK, YOLO, Gazebo subprocesses) are mocked.
- **Integration tests** (`tests/integration/`): Added in Phase 8. Will test full API flows via FastAPI TestClient.

## Running
```bash
pytest                              # all tests
pytest tests/unit/test_wall_follow.py -v   # specific file
pytest -k "test_create"             # by name pattern
```

## Files
- `conftest.py` — Shared fixtures. `in_memory_db` (raw connection), `repo_db` (patches `get_db()` so repositories hit an in-memory connection), `mock_lidar_scan` (factory for LidarScan with configurable sector distances).
- `__init__.py` — Empty, makes tests a package.

## Subdirectories
- `unit/` — Unit tests, one file per source module. Currently: WallFollowController, DistanceStabilizerController, FrontWallDetector, LidarScan, YoloDetector, all 5 repositories. Covers ADD UT-01 through UT-15.

## Key Fixture Detail
`repo_db` wraps the SQLite connection in `_NonClosingConn` so repository code (which calls `conn.close()` after each query in production) doesn't tear down the test's shared in-memory DB between repo calls. The real connection closes at test teardown.
