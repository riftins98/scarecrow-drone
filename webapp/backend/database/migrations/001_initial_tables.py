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
