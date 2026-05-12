"""Simulation lifecycle routes: /api/sim/*"""
import os
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from dependencies import sim_service
from services.script_metadata import (
    list_flight_scripts,
    list_worlds,
    script_info_to_dict,
    world_info_to_dict,
)

router = APIRouter(prefix="/api/sim", tags=["sim"])

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WORLDS_DIR = os.path.join(REPO_ROOT, "worlds")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts", "flight")


class ConnectRequest(BaseModel):
    world: Optional[str] = None
    headless: Optional[bool] = False


@router.post("/connect")
async def connect_sim(req: Optional[ConnectRequest] = None):
    """Launch PX4 + Gazebo (non-blocking, poll /api/sim/status for progress).

    Optional body:
        {"world": "drone_garage_pigeon_3d", "headless": false}
    Defaults match the legacy behavior (drone_garage_pigeon_3d, GUI).
    """
    try:
        world = (req.world if req else None) or "drone_garage_pigeon_3d"
        headless = bool(req.headless) if req else False
        sim_service.launch(world=world, headless=headless)
        return {"success": True, "message": "Simulation launching..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/connect")
async def disconnect_sim():
    sim_service.stop()
    return {"success": True}


@router.get("/status")
async def sim_status():
    return {
        "connected": sim_service.is_connected,
        "launching": sim_service.launching,
        "log": sim_service.get_log(20),
        "progress": sim_service.launch_progress,
        "world": sim_service.world,
        "headless": sim_service.headless,
        "streamUrl": sim_service.stream_url,
    }


@router.get("/options")
async def sim_options():
    """List available worlds + flight scripts (with parsed CLI args).

    Used by the frontend to render the pre-connect world/headless picker and
    the post-connect script picker.
    """
    return {
        "worlds": [world_info_to_dict(w) for w in list_worlds(WORLDS_DIR)],
        "scripts": [script_info_to_dict(s) for s in list_flight_scripts(SCRIPTS_DIR)],
    }
