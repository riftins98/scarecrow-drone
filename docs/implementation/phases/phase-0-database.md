# Phase 0: Database Schema & Migrations

**Dependencies**: None -- start here
**Estimated size**: Small (2 files to create, 1 to modify)

## Goal

Add the 3 missing tables (area_maps, telemetry, chase_events) and the area_map_id column to flights, using an idempotent migration system.

## Pre-read

Before starting, read these files:
- `webapp/backend/database/db.py` -- current schema and init_db()
- `docs/implementation/specs/workflow.md` -- migration rules
- `docs/implementation/specs/security.md` -- parameterized queries

## Tasks

### 1. Create migration runner

**File**: `webapp/backend/database/migrate.py`

```python
"""Idempotent migration runner for SQLite."""
import importlib
import os
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Run all pending migrations in order. Returns list of applied migration names."""
    # Create tracking table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # Find migration files
    migration_files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".py") and not f.startswith("_")
    )

    applied = []
    for filename in migration_files:
        name = filename.replace(".py", "")
        # Check if already applied
        row = conn.execute(
            "SELECT 1 FROM _migrations WHERE name = ?", (name,)
        ).fetchone()
        if row:
            continue

        # Import and run
        spec = importlib.util.spec_from_file_location(
            name, MIGRATIONS_DIR / filename
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.up(conn)

        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        applied.append(name)

    return applied
```

### 2. Create migrations directory and files

**File**: `webapp/backend/database/migrations/__init__.py` (empty)

**File**: `webapp/backend/database/migrations/001_initial_tables.py`

This migration ensures the existing tables exist (idempotent -- safe on both fresh and existing DBs):

```python
"""Migration: ensure initial tables (flights, detection_images) exist."""
import sqlite3

def up(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS flights (
            id TEXT PRIMARY KEY,
            area_map_id INTEGER,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration REAL DEFAULT 0,
            pigeons_detected INTEGER DEFAULT 0,
            frames_processed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'in_progress',
            video_path TEXT
        );
        CREATE TABLE IF NOT EXISTS detection_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_id TEXT NOT NULL,
            image_path TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (flight_id) REFERENCES flights(id)
        );
    """)
```

**File**: `webapp/backend/database/migrations/002_add_area_maps.py`

```python
"""Migration: add area_maps table (ADD Section 3.2.1)."""
import sqlite3

def up(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS area_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            boundaries TEXT,
            area_size REAL,
            status TEXT DEFAULT 'draft'
        );
    """)
```

**File**: `webapp/backend/database/migrations/003_add_telemetry.py`

```python
"""Migration: add telemetry table (ADD Section 3.2.4)."""
import sqlite3

def up(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS telemetry (
            flight_id TEXT PRIMARY KEY,
            battery_level REAL,
            distance REAL NOT NULL DEFAULT 0,
            detections INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (flight_id) REFERENCES flights(id)
        );
    """)
```

**File**: `webapp/backend/database/migrations/004_add_chase_events.py`

```python
"""Migration: add chase_events table (ADD Section 3.2.5)."""
import sqlite3

def up(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chase_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_id TEXT NOT NULL,
            detection_image_id INTEGER,
            start_time TEXT NOT NULL,
            end_time TEXT,
            counter_measure_type TEXT NOT NULL,
            outcome TEXT,
            FOREIGN KEY (flight_id) REFERENCES flights(id),
            FOREIGN KEY (detection_image_id) REFERENCES detection_images(id)
        );
    """)
```

### 3. Update db.py to use migration runner

**File**: `webapp/backend/database/db.py` -- modify `init_db()`:

Replace the inline `CREATE TABLE` executescript with:
```python
from .migrate import run_migrations

def init_db():
    conn = get_db()
    applied = run_migrations(conn)
    if applied:
        print(f"Applied migrations: {applied}")
    conn.close()
```

Keep `get_db()`, `create_flight()`, `end_flight()`, `fail_flight()`, `add_detection_image()`, `get_flights()`, `get_flight()`, `get_flight_images()` unchanged for now -- they will be moved to repositories in Phase 1.

### 4. Handle existing flights table

The existing `flights` table doesn't have `area_map_id`. Migration 001 creates it with the column. For existing DBs where the table already exists, add a column-add migration:

**File**: `webapp/backend/database/migrations/005_flights_add_area_map_id.py`

```python
"""Migration: add area_map_id column to flights (for existing DBs)."""
import sqlite3

def up(conn: sqlite3.Connection):
    # Check if column already exists
    cursor = conn.execute("PRAGMA table_info(flights)")
    columns = [row[1] for row in cursor.fetchall()]
    if "area_map_id" not in columns:
        conn.execute("ALTER TABLE flights ADD COLUMN area_map_id INTEGER")
        conn.commit()
```

## Verification

1. Delete `webapp/backend/database/scarecrow.db` (or rename it to test fresh)
2. Run `cd webapp/backend && python -c "from database.db import init_db; init_db()"`
3. Verify all tables exist: `sqlite3 database/scarecrow.db ".tables"` should show: `_migrations area_maps chase_events detection_images flights telemetry`
4. Run again to verify idempotency -- no errors, no duplicate migrations
5. Test with existing DB: restore the old .db file and run init_db() -- should add new tables without touching existing data

## Decision Log

- **Keep TEXT flight IDs**: UUID-based IDs are wired into detection subprocess protocol (`DETECTION_IMAGE:` stdout parsing) and file system layout (`webapp/output/{flight_id}/`). Changing to INTEGER would break the working pipeline.
- **Keep extra columns in flights** (pigeons_detected, frames_processed, duration): they're actively used by the webapp. The ADD's schema is a target; these additions are pragmatic.
