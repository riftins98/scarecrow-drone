"""Connection routes (ADD A.2): /api/connection/*

For the simulation phase, wifi/ssh return mock "connected" responses since
the drone is simulated. When hardware arrives these will talk to the real
Raspberry Pi companion computer.
"""
from fastapi import APIRouter

from dependencies import recording_service, detection_service, sim_service

router = APIRouter(prefix="/api/connection", tags=["connection"])


@router.get("/wifi")
async def wifi_status():
    return {"connected": True, "ssid": "simulation"}


@router.post("/ssh")
async def ssh_connect():
    return {"success": True}


@router.delete("/ssh")
async def ssh_disconnect():
    return {"success": True}


@router.get("/status")
async def connection_status():
    return {
        "wifiConnected": True,
        "sshConnected": True,
        "droneReady": sim_service.is_connected,
        "streamActive": recording_service.get_status()["recording"],
    }


@router.post("/video/start")
async def video_start():
    flight_id = detection_service.flight_id
    if flight_id:
        recording_service.on_flight_started(flight_id)
    return {"success": True, "streamUrl": None}


@router.post("/video/stop")
async def video_stop():
    recording_service.on_flight_ended()
    return {"success": True}
