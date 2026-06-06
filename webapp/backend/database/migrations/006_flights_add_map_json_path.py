"""Migration: add map_json_path column to flights."""
import sqlite3


def up(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(flights)")
    columns = [row[1] for row in cursor.fetchall()]
    if "map_json_path" not in columns:
        conn.execute("ALTER TABLE flights ADD COLUMN map_json_path TEXT")
