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
