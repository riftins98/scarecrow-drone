"""Detection image repository -- CRUD for detection_images table."""
from datetime import datetime

from dtos.detection_dto import DetectionImageDTO
from .base import BaseRepository


class DetectionImageRepository(BaseRepository):
    def create(self, flight_id: str, image_path: str) -> DetectionImageDTO:
        timestamp = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO detection_images (flight_id, image_path, timestamp) VALUES (?, ?, ?)",
                (flight_id, image_path, timestamp),
            )
            conn.commit()
            new_id = cur.lastrowid
        finally:
            conn.close()
        return DetectionImageDTO(
            id=new_id, flight_id=flight_id, image_path=image_path, timestamp=timestamp,
        )

    def get_by_flight_id(self, flight_id: str) -> list[DetectionImageDTO]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM detection_images WHERE flight_id = ? ORDER BY timestamp",
                (flight_id,),
            ).fetchall()
        finally:
            conn.close()
        return [DetectionImageDTO(**dict(r)) for r in rows]
