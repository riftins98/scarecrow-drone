"""Static file serving: detection images and flight video recordings."""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["static"])

OUTPUT_ROOT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "output")
)


def _safe_path(*parts: str) -> str:
    """Join parts under OUTPUT_ROOT and reject path traversal attempts."""
    candidate = os.path.realpath(os.path.join(OUTPUT_ROOT, *parts))
    if not candidate.startswith(OUTPUT_ROOT):
        raise HTTPException(403, "Access denied")
    return candidate


@router.get("/detection_images/{flight_id}/{filename}")
async def serve_detection_image(flight_id: str, filename: str):
    path = _safe_path(flight_id, "detections", filename)
    if not os.path.exists(path):
        # Fallback for flat layout
        path = _safe_path(flight_id, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Image not found")
    return FileResponse(path)


@router.get("/recordings/{flight_id}/{filename}")
async def serve_recording(flight_id: str, filename: str):
    path = _safe_path(flight_id, filename)
    if not os.path.exists(path):
        raise HTTPException(404, "Recording not found")
    return FileResponse(path, media_type="video/mp4")
