"""Migration: add compact mission summary fields to flights."""
import sqlite3


def up(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(flights)")
    columns = {row[1] for row in cursor.fetchall()}

    if "pigeons_deterred" not in columns:
        conn.execute("ALTER TABLE flights ADD COLUMN pigeons_deterred INTEGER DEFAULT 0")

    if "pursuit_flow_count" not in columns:
        conn.execute("ALTER TABLE flights ADD COLUMN pursuit_flow_count INTEGER DEFAULT 0")
