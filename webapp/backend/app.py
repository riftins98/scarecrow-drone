"""Scarecrow Drone — Simulation Web App Backend."""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database.db import (
    create_flight, end_flight, fail_flight, add_detection_image,
    get_flights, get_flight, get_flight_images
)
from services.sim_service import SimService
from services.detection_service import DetectionService

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output")
os.makedirs(OUTPUT_ROOT, exist_ok=True)

app = FastAPI(title="Scarecrow Drone Sim")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

sim = SimService()
detection = DetectionService()


# --- Sim Connection ---

@app.post("/api/sim/connect")
async def connect_sim():
    """Launch PX4 + Gazebo (non-blocking, poll /api/sim/status for progress)."""
    try:
        sim.launch()
        return {"success": True, "message": "Simulation launching..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/sim/connect")
async def disconnect_sim():
    """Stop simulation."""
    sim.stop()
    return {"success": True}


@app.get("/api/sim/status")
async def sim_status():
    return {
        "connected": sim.is_connected,
        "launching": sim.launching,
        "log": sim.get_log(20),
        "progress": sim.launch_progress,
    }


# --- Detection / Flight Control ---

@app.post("/api/flight/start")
async def start_flight():
    """Start pigeon detection session."""
    if not sim.is_connected:
        raise HTTPException(400, "Simulation not running")
    if detection.running:
        raise HTTPException(400, "Detection already running")

    flight_id = create_flight()

    def on_detection(fid, img_path):
        add_detection_image(fid, img_path)

    ok = detection.start(flight_id, on_detection=on_detection)
    if not ok:
        fail_flight(flight_id)
        raise HTTPException(500, "Failed to start detection")

    return {"success": True, "flightId": flight_id}


@app.post("/api/flight/stop")
async def stop_flight():
    """Stop detection and save results."""
    flight_id = detection.flight_id
    if not flight_id:
        raise HTTPException(400, "No detection session")

    result = detection.stop()

    end_flight(
        flight_id,
        pigeons=result["pigeons_detected"],
        frames=result["frames_processed"],
        video_path=result.get("video_path"),
    )

    return {
        "success": True,
        "flightId": flight_id,
        "pigeonsDetected": result["pigeons_detected"],
        "framesProcessed": result["frames_processed"],
    }


@app.get("/api/flight/status")
async def flight_status():
    # Auto-finalize flight if detection stopped but flight is still "in_progress"
    if not detection.running and detection.flight_id:
        f = get_flight(detection.flight_id)
        if f and f["status"] == "in_progress":
            end_flight(
                detection.flight_id,
                pigeons=detection.pigeons_detected,
                frames=detection.frames_processed,
            )
    return {
        "isFlying": detection.running,
        "isConnected": sim.is_connected,
        **detection.status,
    }


# --- Flight History ---

@app.get("/api/flights")
async def list_flights():
    flights = get_flights()
    return [
        {
            "id": f["id"],
            "date": f["start_time"],
            "startTime": f["start_time"],
            "endTime": f["end_time"],
            "duration": f["duration"],
            "pigeonsDetected": f["pigeons_detected"],
            "framesProcessed": f["frames_processed"],
            "status": f["status"],
            "videoPath": f["video_path"],
        }
        for f in flights
    ]


@app.get("/api/flights/{flight_id}")
async def get_flight_detail(flight_id: str):
    f = get_flight(flight_id)
    if not f:
        raise HTTPException(404, "Flight not found")
    return {
        "id": f["id"],
        "date": f["start_time"],
        "startTime": f["start_time"],
        "endTime": f["end_time"],
        "duration": f["duration"],
        "pigeonsDetected": f["pigeons_detected"],
        "framesProcessed": f["frames_processed"],
        "status": f["status"],
        "videoPath": f["video_path"],
    }


@app.get("/api/flights/{flight_id}/images")
async def get_flight_detection_images(flight_id: str):
    images = get_flight_images(flight_id)
    return {"images": images}


@app.get("/api/flights/{flight_id}/recording")
async def get_flight_recording(flight_id: str):
    f = get_flight(flight_id)
    if not f:
        raise HTTPException(404, "Flight not found")
    return {"recording": f["video_path"]}


# --- File Serving ---

@app.get("/detection_images/{flight_id}/{filename}")
async def serve_detection_image(flight_id: str, filename: str):
    path = os.path.join(OUTPUT_ROOT, flight_id, "detections", filename)
    if not os.path.exists(path):
        # Try flat structure
        path = os.path.join(OUTPUT_ROOT, flight_id, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Image not found")
    return FileResponse(path)


@app.get("/recordings/{flight_id}/{filename}")
async def serve_recording(flight_id: str, filename: str):
    path = os.path.join(OUTPUT_ROOT, flight_id, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Recording not found")
    return FileResponse(path, media_type="video/mp4")


# --- Health ---

@app.get("/api/health")
async def health():
    return {"status": "ok", "sim_connected": sim.is_connected}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
