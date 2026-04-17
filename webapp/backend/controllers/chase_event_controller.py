"""Chase event routes (ADD A.7): /api/flights/{id}/chases, /api/chases/{id}"""
from fastapi import APIRouter, HTTPException

from dependencies import chase_event_service

router = APIRouter(tags=["chases"])


@router.get("/api/flights/{flight_id}/chases")
async def get_flight_chases(flight_id: str):
    chases = chase_event_service.get_chases_for_flight(flight_id)
    return [c.model_dump() for c in chases]


@router.get("/api/chases/{chase_id}")
async def get_chase(chase_id: int):
    chase = chase_event_service.get_chase(chase_id)
    if chase is None:
        raise HTTPException(404, "Chase event not found")
    return chase.model_dump()
