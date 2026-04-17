"""Chase event repository -- CRUD for chase_events table."""
from datetime import datetime
from typing import Optional

from dtos.chase_event_dto import ChaseEventCreateDTO, ChaseEventDTO
from .base import BaseRepository


class ChaseEventRepository(BaseRepository):
    def create(self, dto: ChaseEventCreateDTO) -> ChaseEventDTO:
        start_time = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            cur = conn.execute(
                """INSERT INTO chase_events
                   (flight_id, detection_image_id, start_time, counter_measure_type)
                   VALUES (?, ?, ?, ?)""",
                (dto.flight_id, dto.detection_image_id, start_time, dto.counter_measure_type),
            )
            conn.commit()
            new_id = cur.lastrowid
        finally:
            conn.close()
        return ChaseEventDTO(
            id=new_id,
            flight_id=dto.flight_id,
            detection_image_id=dto.detection_image_id,
            start_time=start_time,
            counter_measure_type=dto.counter_measure_type,
        )

    def get_by_id(self, chase_id: int) -> Optional[ChaseEventDTO]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM chase_events WHERE id = ?", (chase_id,)
            ).fetchone()
        finally:
            conn.close()
        return ChaseEventDTO(**dict(row)) if row else None

    def get_by_flight_id(self, flight_id: str) -> list[ChaseEventDTO]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM chase_events WHERE flight_id = ? ORDER BY start_time",
                (flight_id,),
            ).fetchall()
        finally:
            conn.close()
        return [ChaseEventDTO(**dict(r)) for r in rows]

    def update(self, chase_id: int, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {"end_time", "outcome"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        cols = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [chase_id]
        conn = self._get_conn()
        try:
            conn.execute(f"UPDATE chase_events SET {cols} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()
