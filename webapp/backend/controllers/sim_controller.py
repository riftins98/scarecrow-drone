"""Simulation lifecycle routes: /api/sim/*"""
from fastapi import APIRouter

from dependencies import sim_service

router = APIRouter(prefix="/api/sim", tags=["sim"])


@router.post("/connect")
async def connect_sim():
    """Launch PX4 + Gazebo (non-blocking, poll /api/sim/status for progress)."""
    try:
        sim_service.launch()
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
    }
