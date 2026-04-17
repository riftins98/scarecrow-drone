"""Shared test fixtures."""
import math
from unittest.mock import patch

import numpy as np
import pytest


@pytest.fixture
def in_memory_db():
    """In-memory SQLite connection with full schema applied via migrations.

    Use this when you want direct DB access in a test. For repository tests,
    use `repo_db` which also patches `get_db()` so repos use the same connection.
    """
    import sqlite3
    from database.migrate import run_migrations

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    run_migrations(conn)
    yield conn
    conn.close()


class _NonClosingConn:
    """Wraps a real sqlite3 connection but ignores close() calls.

    Repositories call conn.close() on each operation. For tests we want
    the connection to persist across calls, so we swallow close() and
    tear it down in the fixture teardown.
    """

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        # Swallow close() so the connection persists across repo calls
        return None

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def repo_db():
    """Patches `get_db()` to return a shared in-memory connection.

    Lets repositories work against a disposable DB without touching the
    real scarecrow.db file. The wrapper ignores close() so the connection
    persists for the duration of the test.
    """
    import sqlite3
    from database.migrate import run_migrations

    real_conn = sqlite3.connect(":memory:")
    real_conn.row_factory = sqlite3.Row
    run_migrations(real_conn)

    wrapped = _NonClosingConn(real_conn)

    def _fake_get_db():
        return wrapped

    with patch("database.db.get_db", _fake_get_db), \
         patch("repositories.base.get_db", _fake_get_db):
        yield real_conn

    real_conn.close()


@pytest.fixture
def mock_lidar_scan():
    """Factory for LidarScan with configurable sector distances.

    Usage:
        scan = mock_lidar_scan(front=3.0, left=2.0)
    """
    from scarecrow.sensors.lidar.base import LidarScan

    def _make(front=5.0, rear=5.0, left=2.0, right=8.0, num_samples=1440):
        angles = np.linspace(-math.pi, math.pi, num_samples, endpoint=False)
        ranges = np.full(num_samples, 10.0, dtype=np.float64)

        for i, a in enumerate(angles):
            a_wrapped = float(a)
            if abs(a_wrapped) < 0.2:
                ranges[i] = front
            elif abs(abs(a_wrapped) - math.pi) < 0.2:
                ranges[i] = rear
            elif abs(a_wrapped - math.pi / 2) < 0.2:
                ranges[i] = left
            elif abs(a_wrapped + math.pi / 2) < 0.2:
                ranges[i] = right
        return LidarScan(ranges=ranges)

    return _make
