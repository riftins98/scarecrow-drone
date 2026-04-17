"""Telemetry repository -- 1:1 with flights."""
from typing import Optional

from dtos.telemetry_dto import TelemetryCreateDTO, TelemetryDTO
from .base import BaseRepository


class TelemetryRepository(BaseRepository):
    def create(self, dto: TelemetryCreateDTO) -> TelemetryDTO:
        conn = self._get_conn()
        try:
            conn.execute(
                "INSERT INTO telemetry (flight_id, battery_level, distance, detections) VALUES (?, ?, ?, ?)",
                (dto.flight_id, dto.battery_level, dto.distance, dto.detections),
            )
            conn.commit()
        finally:
            conn.close()
        return TelemetryDTO(**dto.model_dump())

    def get_by_flight_id(self, flight_id: str) -> Optional[TelemetryDTO]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM telemetry WHERE flight_id = ?", (flight_id,)
            ).fetchone()
        finally:
            conn.close()
        return TelemetryDTO(**dict(row)) if row else None

    def update(self, flight_id: str, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {"battery_level", "distance", "detections"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        cols = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [flight_id]
        conn = self._get_conn()
        try:
            conn.execute(f"UPDATE telemetry SET {cols} WHERE flight_id = ?", values)
            conn.commit()
        finally:
            conn.close()
