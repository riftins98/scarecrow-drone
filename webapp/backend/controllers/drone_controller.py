"""Drone control routes (ADD A.3): /api/drone/*"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dependencies import (
    sim_service,
    detection_service,
    flight_service,
    drone_service,
)
from repositories import DetectionImageRepository

router = APIRouter(prefix="/api/drone", tags=["drone"])

_detection_image_repo = DetectionImageRepository()


class StartDroneRequest(BaseModel):
    areaMapId: Optional[int] = None


@router.get("/status")
async def drone_status():
    return drone_service.get_status()


@router.post("/start")
async def start_drone(req: Optional[StartDroneRequest] = None):
    """Start a detection flight. Optionally linked to an area map."""
    if not sim_service.is_connected:
        raise HTTPException(400, "Simulation not running")
    if detection_service.running:
        raise HTTPException(400, "Flight already in progress")

    area_map_id = req.areaMapId if req else None
    flight = flight_service.create_flight(area_map_id=area_map_id)

    def on_detection(fid, img_path):
        _detection_image_repo.create(fid, img_path)

    ok = drone_service.start_flight(flight.id, on_detection=on_detection)
    if not ok:
        flight_service.flight_repo.fail_flight(flight.id)
        raise HTTPException(500, "Failed to start flight")

    return {"success": True, "flightId": flight.id}


@router.post("/stop")
async def stop_drone():
    flight_id = drone_service.current_flight_id
    if not flight_id:
        raise HTTPException(400, "No active flight")

    updated = flight_service.stop_flight(flight_id)
    return {
        "success": True,
        "pigeonsDetected": updated.pigeons_detected,
        "framesProcessed": updated.frames_processed,
    }


@router.post("/abort")
async def abort_drone():
    """Emergency abort -- stops flight, marks aborted, commands safe landing."""
    flight_id = drone_service.current_flight_id
    if not flight_id:
        raise HTTPException(400, "No active flight")

    drone_service.abort()
    aborted = flight_service.abort_flight(flight_id)
    if aborted is None:
        raise HTTPException(500, "Abort failed")
    return {
        "success": True,
        "pigeonsDetected": aborted.pigeons_detected,
        "framesProcessed": aborted.frames_processed,
    }


@router.post("/return-home")
async def return_home():
    ok = drone_service.return_home()
    return {"success": ok}


@router.get("/telemetry")
async def get_telemetry():
    return drone_service.get_telemetry()
