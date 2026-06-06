"""Migration: ensure map_path exists; copy from map_image_path if upgrading."""
import sqlite3


def up(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(flights)")
    columns = [row[1] for row in cursor.fetchall()]
    if "map_path" not in columns:
        conn.execute("ALTER TABLE flights ADD COLUMN map_path TEXT")
    if "map_image_path" in columns:
        conn.execute(
            "UPDATE flights SET map_path = map_image_path "
            "WHERE map_path IS NULL AND map_image_path IS NOT NULL"
        )
