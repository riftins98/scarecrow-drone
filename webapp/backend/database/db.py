"""SQLite database for flight history, detection images, and recordings."""
import os
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "scarecrow.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS flights (
            id TEXT PRIMARY KEY,
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
    conn.commit()
    conn.close()


def create_flight() -> str:
    flight_id = str(uuid.uuid4())[:8]
    conn = get_db()
    conn.execute(
        "INSERT INTO flights (id, start_time, status) VALUES (?, ?, ?)",
        (flight_id, datetime.now().isoformat(), "in_progress")
    )
    conn.commit()
    conn.close()
    return flight_id


def end_flight(flight_id: str, pigeons: int, frames: int, video_path: Optional[str] = None):
    conn = get_db()
    now = datetime.now().isoformat()
    row = conn.execute("SELECT start_time FROM flights WHERE id = ?", (flight_id,)).fetchone()
    duration = 0
    if row:
        start = datetime.fromisoformat(row["start_time"])
        duration = (datetime.now() - start).total_seconds()
    conn.execute(
        """UPDATE flights SET end_time=?, duration=?, pigeons_detected=?,
           frames_processed=?, status=?, video_path=? WHERE id=?""",
        (now, duration, pigeons, frames, "completed", video_path, flight_id)
    )
    conn.commit()
    conn.close()


def fail_flight(flight_id: str):
    conn = get_db()
    conn.execute(
        "UPDATE flights SET status='failed', end_time=? WHERE id=?",
        (datetime.now().isoformat(), flight_id)
    )
    conn.commit()
    conn.close()


def add_detection_image(flight_id: str, image_path: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO detection_images (flight_id, image_path, timestamp) VALUES (?, ?, ?)",
        (flight_id, image_path, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def get_flights() -> List[Dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM flights ORDER BY start_time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_flight(flight_id: str) -> Optional[Dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM flights WHERE id = ?", (flight_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_flight_images(flight_id: str) -> List[str]:
    conn = get_db()
    rows = conn.execute(
        "SELECT image_path FROM detection_images WHERE flight_id = ? ORDER BY timestamp",
        (flight_id,)
    ).fetchall()
    conn.close()
    return [r["image_path"] for r in rows]


# Initialize on import
init_db()
