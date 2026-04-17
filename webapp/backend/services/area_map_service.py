"""Area map management for UC1 (Map Area).

CRUD operations today. Phase 3 (UC1) will add `start_mapping()` which spawns
the mapping flight subprocess; stubbed here for now.
"""
from typing import Optional

from dtos.area_map_dto import AreaMapCreateDTO, AreaMapDTO
from dtos.flight_dto import FlightDTO
from repositories import AreaMapRepository


class AreaMapService:
    def __init__(self, area_map_repo: Optional[AreaMapRepository] = None):
        self.area_map_repo = area_map_repo or AreaMapRepository()
        self._mapping_active = False
        self._current_map_id: Optional[int] = None
        self._mapping_status = "idle"

    def create_map(self, dto: AreaMapCreateDTO) -> AreaMapDTO:
        return self.area_map_repo.create(dto)

    def get_map(self, map_id: int) -> Optional[AreaMapDTO]:
        return self.area_map_repo.get_by_id(map_id)

    def get_all_maps(self) -> list[AreaMapDTO]:
        return self.area_map_repo.get_all()

    def update_map(self, map_id: int, **kwargs) -> Optional[AreaMapDTO]:
        self.area_map_repo.update(map_id, **kwargs)
        return self.area_map_repo.get_by_id(map_id)

    def delete_map(self, map_id: int) -> bool:
        return self.area_map_repo.delete(map_id)

    def get_flights_for_area(self, map_id: int) -> list[FlightDTO]:
        return self.area_map_repo.get_flights_for_area(map_id)

    def start_mapping(self, name: str) -> dict:
        """Stub for Phase 3 (UC1). Creates the area_map record but mapping
        flight subprocess spawning is implemented in the UC1 phase."""
        if self._mapping_active:
            return {"success": False, "error": "Mapping already in progress"}
        area = self.area_map_repo.create(AreaMapCreateDTO(name=name))
        self.area_map_repo.update(area.id, status="mapping_in_progress")
        self._current_map_id = area.id
        self._mapping_active = False  # Real subprocess spawn in Phase 3
        self._mapping_status = "stub_not_implemented"
        return {
            "success": True,
            "mappingId": area.id,
            "note": "mapping subprocess stubbed -- implemented in Phase 3 UC1",
        }

    def get_mapping_status(self) -> dict:
        return {
            "active": self._mapping_active,
            "mapId": self._current_map_id,
            "status": self._mapping_status,
        }
