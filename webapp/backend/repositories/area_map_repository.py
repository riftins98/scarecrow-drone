"""Area map repository -- CRUD for area_maps table."""
from datetime import datetime
from typing import Optional

from dtos.area_map_dto import AreaMapCreateDTO, AreaMapDTO
from dtos.flight_dto import FlightDTO
from .base import BaseRepository


class AreaMapRepository(BaseRepository):
    def create(self, dto: AreaMapCreateDTO) -> AreaMapDTO:
        now = datetime.now().isoformat()
        conn = self._get_conn()
        try:
            cur = conn.execute(
                "INSERT INTO area_maps (name, created_at, updated_at, boundaries) VALUES (?, ?, ?, ?)",
                (dto.name, now, now, dto.boundaries),
            )
            conn.commit()
            new_id = cur.lastrowid
        finally:
            conn.close()
        return AreaMapDTO(
            id=new_id, name=dto.name, created_at=now, updated_at=now,
            boundaries=dto.boundaries, status="draft",
        )

    def get_by_id(self, area_map_id: int) -> Optional[AreaMapDTO]:
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM area_maps WHERE id = ?", (area_map_id,)
            ).fetchone()
        finally:
            conn.close()
        return AreaMapDTO(**dict(row)) if row else None

    def get_all(self) -> list[AreaMapDTO]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM area_maps ORDER BY created_at DESC"
            ).fetchall()
        finally:
            conn.close()
        return [AreaMapDTO(**dict(r)) for r in rows]

    def update(self, area_map_id: int, **kwargs) -> None:
        if not kwargs:
            return
        allowed = {"name", "boundaries", "area_size", "status"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        updates["updated_at"] = datetime.now().isoformat()
        cols = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [area_map_id]
        conn = self._get_conn()
        try:
            conn.execute(f"UPDATE area_maps SET {cols} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def delete(self, area_map_id: int) -> bool:
        conn = self._get_conn()
        try:
            cur = conn.execute("DELETE FROM area_maps WHERE id = ?", (area_map_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_flights_for_area(self, area_map_id: int) -> list[FlightDTO]:
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM flights WHERE area_map_id = ? ORDER BY start_time DESC",
                (area_map_id,),
            ).fetchall()
        finally:
            conn.close()
        return [FlightDTO(**dict(r)) for r in rows]
