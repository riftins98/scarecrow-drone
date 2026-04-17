"""Idempotent migration runner for SQLite.

Discovers migration files in `migrations/`, tracks applied ones in `_migrations`
table, runs pending migrations in sorted order. Safe to run repeatedly.
"""
import importlib.util
import os
import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(conn: sqlite3.Connection) -> list[str]:
    """Run all pending migrations in order. Returns list of applied migration names."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    migration_files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".py") and not f.startswith("_")
    )

    applied = []
    for filename in migration_files:
        name = filename.replace(".py", "")
        row = conn.execute(
            "SELECT 1 FROM _migrations WHERE name = ?", (name,)
        ).fetchone()
        if row:
            continue

        spec = importlib.util.spec_from_file_location(name, MIGRATIONS_DIR / filename)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.up(conn)

        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        applied.append(name)

    return applied
