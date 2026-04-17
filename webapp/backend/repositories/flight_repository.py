"""Flight repository -- CRUD for flights table."""
import uuid
from datetime import datetime
from typing import Optional

from dtos.flight_dto import FlightDTO
from .base import BaseRepository


class FlightRepository(BaseRepository):
    def create(self, area_map_id: Optional[int] = None) -> FlightDTO:
        flight_id = str(uuid.uuid4())[:8]
        start_time = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO flights (id, area_map_id, start_time, status) VALUES (?, ?, ?, ?)",
                (flight_id, area_map_id, start_time, "in_progress"),
            )
            conn.commit()
        finally:
            conn.close()
        return FlightDTO(id=flight_id, area_map_id=area_map_id, start_time=start_time)

    def get_by_id(self, flight_id: str) -> Optional[FlightDTO]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM flights WHERE id = ?", (flight_id,)
            ).fetchone()
        finally:
            conn.close()
        return FlightDTO(**dict(row)) if row else None

    def get_all(self) -> list[FlightDTO]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM flights ORDER BY start_time DESC"
            ).fetchall()
        finally:
            conn.close()
        return [FlightDTO(**dict(r)) for r in rows]

    def update(self, flight_id: str, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {
            "area_map_id", "start_time", "end_time", "duration",
            "pigeons_detected", "frames_processed", "status", "video_path",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        cols = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [flight_id]
        conn = self._get_conn()
        try:
            conn.execute(f"UPDATE flights SET {cols} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def delete(self, flight_id: str) -> bool:
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM flights WHERE id = ?", (flight_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def end_flight(
        self,
        flight_id: str,
        pigeons: int,
        frames: int,
        video_path: Optional[str] = None,
    ) -> None:
        """Mark a flight completed. Computes duration from start_time."""
        now = datetime.now()
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT start_time FROM flights WHERE id = ?", (flight_id,)
            ).fetchone()
            duration = 0.0
            if row:
                duration = (now - datetime.fromisoformat(row["start_time"])).total_seconds()
            conn.execute(
                """UPDATE flights SET end_time=?, duration=?, pigeons_detected=?,
                   frames_processed=?, status=?, video_path=? WHERE id=?""",
                (now.isoformat(), duration, pigeons, frames, "completed", video_path, flight_id),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_flight(self, flight_id: str) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                "UPDATE flights SET status='failed', end_time=? WHERE id=?",
                (datetime.now().isoformat(), flight_id),
            )
            conn.commit()
        finally:
            conn.close()
