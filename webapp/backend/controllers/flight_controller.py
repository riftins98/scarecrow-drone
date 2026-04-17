"""Flight history and legacy flight control routes.

Covers:
  - Legacy (kept for frontend compatibility): /api/flight/start, /stop, /status
  - ADD A.4 flight history: /api/flights, /api/flights/{id}, /summary, /telemetry, /images, /recording, DELETE
"""
from fastapi import APIRouter, HTTPException

from dependencies import (
    sim_service,
    detection_service,
    flight_service,
    telemetry_service,
)
from repositories import DetectionImageRepository

router = APIRouter(tags=["flights"])

_detection_image_repo = DetectionImageRepository()


# --- Legacy detection-flight endpoints (used by existing frontend) ---

@router.post("/api/flight/start")
async def start_flight_legacy():
    """Start pigeon detection session (legacy endpoint, kept for current frontend)."""
    if not sim_service.is_connected:
        raise HTTPException(400, "Simulation not running")
    if detection_service.running:
        raise HTTPException(400, "Detection already running")

    flight = flight_service.create_flight()

    def on_detection(fid, img_path):
        _detection_image_repo.create(fid, img_path)

    ok = flight_service.start_detection(flight.id, on_detection=on_detection)
    if not ok:
        flight_service.flight_repo.fail_flight(flight.id)
        raise HTTPException(500, "Failed to start detection")

    return {"success": True, "flightId": flight.id}


@router.post("/api/flight/stop")
async def stop_flight_legacy():
    """Stop detection and save results."""
    flight_id = detection_service.flight_id
    if not flight_id:
        raise HTTPException(400, "No detection session")

    updated = flight_service.stop_flight(flight_id)
    return {
        "success": True,
        "flightId": updated.id,
        "pigeonsDetected": updated.pigeons_detected,
        "framesProcessed": updated.frames_processed,
    }


@router.get("/api/flight/status")
async def flight_status():
    """Current detection status. Auto-finalizes if subprocess exited."""
    # Auto-finalize flight if detection stopped but flight is still "in_progress"
    if not detection_service.running and detection_service.flight_id:
        flight = flight_service.get_flight(detection_service.flight_id)
        if flight and flight.status == "in_progress":
            flight_service.flight_repo.end_flight(
                detection_service.flight_id,
                pigeons=detection_service.pigeons_detected,
                frames=detection_service.frames_processed,
            )
    return {
        "isFlying": detection_service.running,
        "isConnected": sim_service.is_connected,
        **detection_service.status,
    }


# --- ADD A.4 flight history endpoints ---

def _to_frontend_dict(flight):
    """Convert FlightDTO to the camelCase shape the frontend expects."""
    return {
        "id": flight.id,
        "date": flight.start_time,
        "startTime": flight.start_time,
        "endTime": flight.end_time,
        "duration": flight.duration,
        "pigeonsDetected": flight.pigeons_detected,
        "framesProcessed": flight.frames_processed,
        "status": flight.status,
        "videoPath": flight.video_path,
        "areaMapId": flight.area_map_id,
    }


@router.get("/api/flights")
async def list_flights():
    flights = flight_service.get_all_flights()
    return [_to_frontend_dict(f) for f in flights]


@router.get("/api/flights/{flight_id}")
async def get_flight_detail(flight_id: str):
    flight = flight_service.get_flight(flight_id)
    if flight is None:
        raise HTTPException(404, "Flight not found")
    return _to_frontend_dict(flight)


@router.get("/api/flights/{flight_id}/summary")
async def get_flight_summary(flight_id: str):
    summary = flight_service.get_flight_summary(flight_id)
    if summary is None:
        raise HTTPException(404, "Flight not found")
    return summary.model_dump()


@router.get("/api/flights/{flight_id}/telemetry")
async def get_flight_telemetry(flight_id: str):
    telemetry = telemetry_service.get_telemetry(flight_id)
    if telemetry is None:
        raise HTTPException(404, "Telemetry not found")
    return telemetry.model_dump()


@router.get("/api/flights/{flight_id}/images")
async def get_flight_images(flight_id: str):
    images = _detection_image_repo.get_by_flight_id(flight_id)
    return {"images": [img.image_path for img in images]}


@router.get("/api/flights/{flight_id}/recording")
async def get_flight_recording(flight_id: str):
    flight = flight_service.get_flight(flight_id)
    if flight is None:
        raise HTTPException(404, "Flight not found")
    return {"recording": flight.video_path}


@router.delete("/api/flights/{flight_id}")
async def delete_flight(flight_id: str):
    ok = flight_service.delete_flight(flight_id)
    if not ok:
        raise HTTPException(404, "Flight not found")
    return {"success": True}
