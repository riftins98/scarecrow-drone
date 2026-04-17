"""Migration: add area_map_id column to flights (for existing DBs).

Migration 001 creates flights with area_map_id already present for fresh DBs.
This migration handles the case where flights already exists from before
the migration system was introduced — the column didn't exist then.
"""
import sqlite3


def up(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(flights)")
    columns = [row[1] for row in cursor.fetchall()]
    if "area_map_id" not in columns:
        conn.execute("ALTER TABLE flights ADD COLUMN area_map_id INTEGER")
