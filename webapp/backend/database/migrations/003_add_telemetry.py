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
