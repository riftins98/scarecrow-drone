"""Area map routes (ADD A.5): /api/areas/*"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dependencies import area_map_service
from dtos import AreaMapCreateDTO

router = APIRouter(prefix="/api/areas", tags=["areas"])


class StartMappingRequest(BaseModel):
    name: str


class UpdateAreaRequest(BaseModel):
    name: Optional[str] = None
    boundaries: Optional[str] = None
    area_size: Optional[float] = None
    status: Optional[str] = None


# Note: /mapping/* routes must come before /{map_id} to avoid path conflicts

@router.post("/mapping/start")
async def start_mapping(req: StartMappingRequest):
    return area_map_service.start_mapping(req.name)


@router.get("/mapping/status")
async def mapping_status():
    return area_map_service.get_mapping_status()


@router.get("")
async def list_areas():
    areas = area_map_service.get_all_maps()
    return [a.model_dump() for a in areas]


@router.get("/{map_id}")
async def get_area(map_id: int):
    area = area_map_service.get_map(map_id)
    if area is None:
        raise HTTPException(404, "Area map not found")
    return area.model_dump()


@router.post("")
async def create_area(dto: AreaMapCreateDTO):
    area = area_map_service.create_map(dto)
    return area.model_dump()


@router.put("/{map_id}")
async def update_area(map_id: int, req: UpdateAreaRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    updated = area_map_service.update_map(map_id, **updates)
    if updated is None:
        raise HTTPException(404, "Area map not found")
    return updated.model_dump()


@router.delete("/{map_id}")
async def delete_area(map_id: int):
    ok = area_map_service.delete_map(map_id)
    if not ok:
        raise HTTPException(404, "Area map not found")
    return {"success": True}


@router.get("/{map_id}/flights")
async def get_area_flights(map_id: int):
    flights = area_map_service.get_flights_for_area(map_id)
    return [f.model_dump() for f in flights]
