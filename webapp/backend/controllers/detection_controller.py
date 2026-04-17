"""Detection configuration routes (ADD A.6): /api/detection/*"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from dependencies import detection_service

router = APIRouter(prefix="/api/detection", tags=["detection"])

# Detection config is in-memory for now (no persistence needed yet)
_config = {"confidence_threshold": 0.3, "model_path": None}


class UpdateConfigRequest(BaseModel):
    confidence_threshold: Optional[float] = None


@router.get("/status")
async def detection_status():
    return {
        "running": detection_service.running,
        "flightId": detection_service.flight_id,
        "detectionCount": detection_service.pigeons_detected,
    }


@router.get("/config")
async def get_config():
    return _config


@router.put("/config")
async def update_config(req: UpdateConfigRequest):
    if req.confidence_threshold is not None:
        if not 0 <= req.confidence_threshold <= 1:
            return {"success": False, "error": "confidence_threshold must be between 0 and 1"}
        _config["confidence_threshold"] = req.confidence_threshold
    return {"success": True, "config": _config}
