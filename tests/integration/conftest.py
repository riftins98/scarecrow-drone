"""Integration test fixtures.

Key pattern:
- Patch `database.db.get_db` to return an in-memory SQLite connection
- Reset service singletons (SimService, DetectionService state) before each test
- Use FastAPI TestClient for HTTP-level assertions
- NEVER spawn real subprocesses -- mock subprocess.Popen for sim/flight tests
"""
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


class _NonClosingConn:
    """Same wrapper as unit tests -- swallows close() so the connection
    persists across repository calls within a single test."""
    def __init__(self, conn):
        self._conn = conn

    def close(self):
        return None

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def api_client():
    """FastAPI TestClient with in-memory DB and reset service state.

    Usage:
        def test_something(api_client):
            response = api_client.get("/api/health")
            assert response.status_code == 200
    """
    from database.migrate import run_migrations

    # check_same_thread=False because FastAPI TestClient runs requests on a
    # different thread than the fixture. Safe here because only one request
    # runs at a time in tests.
    real_conn = sqlite3.connect(":memory:", check_same_thread=False)
    real_conn.row_factory = sqlite3.Row
    run_migrations(real_conn)
    wrapped = _NonClosingConn(real_conn)

    def _fake_get_db():
        return wrapped

    with patch("database.db.get_db", _fake_get_db), \
         patch("repositories.base.get_db", _fake_get_db):

        # Import app AFTER patching so services that might initialize
        # at import time pick up the patched get_db
        from app import app
        from dependencies import (
            detection_service, sim_service, drone_service,
            flight_service, area_map_service, chase_event_service,
            telemetry_service, recording_service,
        )

        # Reset any state left over from previous tests or app startup
        detection_service.running = False
        detection_service.process = None
        detection_service.flight_id = None
        detection_service.pigeons_detected = 0
        detection_service.frames_processed = 0
        detection_service.detection_images = []
        detection_service._output_lines = []

        # SimService state (the real one -- not mocked unless a test mocks it)
        sim_service.process = None
        sim_service.connected = False
        sim_service.launching = False
        sim_service._log_lines = []
        sim_service._completed_steps = []
        sim_service._current_step = None

        drone_service._latest_telemetry = {}

        area_map_service._mapping_active = False
        area_map_service._current_map_id = None
        area_map_service._mapping_status = "idle"

        client = TestClient(app)
        yield client

    real_conn.close()


@pytest.fixture
def mock_subprocess_popen():
    """Mock subprocess.Popen so no real flight script or PX4 is launched.

    Returns a MagicMock that tests can configure. Example:
        def test_start(api_client, mock_subprocess_popen):
            mock_subprocess_popen.return_value.poll.return_value = None
            response = api_client.post("/api/flight/start")
    """
    from unittest.mock import MagicMock
    with patch("subprocess.Popen") as mock_popen:
        fake_process = MagicMock()
        fake_process.poll.return_value = None  # still running
        fake_process.stdout = iter([])  # no output
        fake_process.pid = 99999
        mock_popen.return_value = fake_process
        yield mock_popen
