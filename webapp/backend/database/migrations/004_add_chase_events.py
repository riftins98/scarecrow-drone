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
