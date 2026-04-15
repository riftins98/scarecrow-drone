# Testing Spec

Requirements for test coverage on all code changes.

## Principles

1. Never make real external API calls in tests -- mock MAVSDK, Gazebo, YOLO, all subprocess calls
2. Test both success and error paths for every function with logic
3. Tests must be deterministic -- no reliance on wall-clock time, random values, or external state
4. If a test fails, fix the code -- never skip tests or mark expected-to-fail
5. Clean up test data safely

## Test Infrastructure

### conftest.py Fixtures

```python
# tests/conftest.py
import pytest
import sqlite3
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

@pytest.fixture
def db():
    """In-memory SQLite database with full schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Run all migrations against in-memory DB
    from webapp.backend.database.migrate import run_migrations
    run_migrations(conn)
    yield conn
    conn.close()

@pytest.fixture
def mock_lidar_scan():
    """Create a LidarScan with configurable distances."""
    import numpy as np
    from scarecrow.sensors.lidar.base import LidarScan

    def _make_scan(front=5.0, rear=5.0, left=2.0, right=8.0, num_samples=1440):
        angles = np.linspace(-np.pi, np.pi, num_samples, endpoint=False)
        ranges = np.full(num_samples, 10.0)
        # Set approximate sector values
        # front = around 0 rad, rear = around pi, left = pi/2, right = -pi/2
        for i, a in enumerate(angles):
            if abs(a) < 0.15:
                ranges[i] = front
            elif abs(a - np.pi) < 0.15 or abs(a + np.pi) < 0.15:
                ranges[i] = rear
            elif abs(a - np.pi/2) < 0.15:
                ranges[i] = left
            elif abs(a + np.pi/2) < 0.15:
                ranges[i] = right
        return LidarScan(ranges=ranges, angles=angles)

    return _make_scan
```

### Mocking External Services

- **MAVSDK**: Mock `mavsdk.System` -- never connect to real PX4
- **Gazebo**: Mock `gz topic` CLI calls -- never spawn real Gazebo
- **YOLO/ultralytics**: Mock model inference -- never load real model weights
- **Subprocess calls**: Mock `subprocess.Popen` for flight script spawning
- **File system**: Use `tmp_path` fixture for output directories

### Pattern for mocking MAVSDK

```python
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_drone():
    drone = MagicMock()
    drone.offboard.set_velocity_body = AsyncMock()
    drone.action.arm = AsyncMock()
    drone.action.takeoff = AsyncMock()
    drone.action.land = AsyncMock()
    drone.telemetry.position_velocity_ned = AsyncMock(return_value=mock_position)
    return drone
```

## Test Organization

### Unit Tests (`tests/unit/`)
- Mirror the source directory structure
- Pure functions with no external dependencies
- Fast -- should run in milliseconds
- File naming: `test_{module_name}.py`

### Integration Tests (`tests/integration/`)
- Test API endpoints end-to-end via FastAPI TestClient
- Use in-memory SQLite DB
- Mock all subprocess/external calls
- Test: valid requests, bad input (4xx not 5xx), missing resources (404)

### Integration test pattern

```python
import pytest
from httpx import AsyncClient, ASGITransport
from webapp.backend.app import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_list_flights(client):
    response = await client.get("/api/flights")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

## What to Test Per Change Type

| Change | Required Tests |
|--------|---------------|
| New API endpoint | Integration: happy path, error cases, bad input |
| New DB query/repository | Unit: correct data returned, edge cases |
| New controller class | Unit: output values for known inputs, edge cases, done conditions |
| New service | Unit with mocked dependencies: success path, error handling |
| Bug fix | Regression test proving the bug is fixed |

## Test Naming

- File: `test_{module_name}.py`
- Function: `test_{scenario}` -- describe the behavior being tested
- Examples: `test_wall_follow_stops_at_front_wall`, `test_create_flight_returns_id`, `test_abort_sets_status_aborted`

## Build Verification (before commit)

- Backend: `python -c "from webapp.backend.app import app"` must succeed
- Frontend (if modified): `cd webapp/frontend && npm run build` must succeed
- All tests: `python -m pytest tests/ -x -q` must pass with zero failures
