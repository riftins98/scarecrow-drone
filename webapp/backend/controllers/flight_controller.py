"""Flight history and legacy flight control routes.

Covers:
  - Legacy (kept for frontend compatibility): /api/flight/start, /stop, /status
  - ADD A.4 flight history: /api/flights, /api/flights/{id}, /summary, /telemetry, /images, /recording, DELETE
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dependencies import (
    sim_service,
    detection_service,
    flight_service,
    telemetry_service,
)
from repositories import DetectionImageRepository
from services.detection_service import resolve_map_path_for_flight

router = APIRouter(tags=["flights"])

_detection_image_repo = DetectionImageRepository()


class FlightStartRequest(BaseModel):
    script: Optional[str] = None             # filename inside scripts/flight/
    args: Optional[dict] = None              # {arg_name: value, ...}


# --- Legacy detection-flight endpoints (used by existing frontend) ---

@router.post("/api/flight/start")
async def start_flight_legacy(req: Optional[FlightStartRequest] = None):
    """Start a flight script as a subprocess.

    Optional body:
        {"script": "demo_flight_v2.py", "args": {"target_alt": 2.0}}
    No body / empty body falls back to demo_flight_v2.py with no args.
    """
    if not sim_service.is_connected:
        raise HTTPException(400, "Simulation not running")
    if detection_service.running:
        raise HTTPException(400, "Detection already running")

    flight = flight_service.create_flight()

    def on_detection(fid, img_path):
        _detection_image_repo.create(fid, img_path)

    script = (req.script if req else None) or "demo_flight_v2.py"
    args = (req.args if req else None) or {}

    ok = flight_service.start_detection(
        flight.id,
        on_detection=on_detection,
        script_name=script,
        script_args=args,
    )
    if not ok:
        flight_service.flight_repo.fail_flight(flight.id)
        # Bubble up the detection_service error so the user knows why
        raise HTTPException(
            500,
            detection_service._last_error or "Failed to start detection",
        )

    return {
        "success": True,
        "flightId": flight.id,
        "script": script,
        "args": args,
    }


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
    """Current detection status. Auto-finalizes if subprocess exited, and
    patches the video_path onto the flight record once it becomes available
    (the subprocess may build the video AFTER stop_flight() already wrote
    the DB, so we keep checking while polling)."""
    if not detection_service.running and detection_service.flight_id:
        flight = flight_service.get_flight(detection_service.flight_id)
        if flight:
            # Resolve the video path from the service tracker OR disk fallback.
            video_path = detection_service.video_path
            if not video_path:
                import os
                video_file = os.path.realpath(os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..", "..", "output",
                    detection_service.flight_id, "flight_camera.mp4",
                ))
                if os.path.exists(video_file):
                    video_path = video_file
                    detection_service.video_path = video_path  # cache

            map_path = detection_service.map_path
            if not map_path:
                map_path = resolve_map_path_for_flight(detection_service.flight_id)
                if map_path:
                    detection_service.map_path = map_path

            if flight.status == "in_progress":
                # Subprocess exited without explicit stop -- finalize now.
                flight_service.flight_repo.end_flight(
                    detection_service.flight_id,
                    pigeons=detection_service.pigeons_detected,
                    frames=detection_service.frames_processed,
                    video_path=video_path,
                    map_path=map_path,
                )
            else:
                patch = {}
                if video_path and not flight.video_path:
                    patch["video_path"] = video_path
                if map_path and not flight.map_path:
                    patch["map_path"] = map_path
                if patch:
                    flight_service.flight_repo.update(
                        detection_service.flight_id, **patch
                    )
    return {
        "isFlying": detection_service.running,
        "isConnected": sim_service.is_connected,
        **detection_service.status,
    }


@router.get("/api/flight/log")
async def flight_log(since: int = 0):
    """Flight-script stdout for SystemLog after the sim is connected."""
    return detection_service.get_log(since=since)


@router.get("/api/flight/log/view", response_class=HTMLResponse)
async def flight_log_view():
    """Standalone page that tails the live flight-script log."""
    return _FLIGHT_LOG_VIEW_HTML


_FLIGHT_LOG_VIEW_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scarecrow // Flight Script Log</title>
<style>
  :root { --bg: #0a0d08; --border: #2a3a1a; --text: #c0c0c0; --muted: #707070; --olive: #8b9a5b; --warn: #d8a05a; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; background: var(--bg); color: var(--text); font-family: Consolas, monospace; font-size: 13px; }
  body { display: flex; flex-direction: column; }
  header { display: flex; gap: 14px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--border); }
  h1 { color: var(--olive); font-size: 13px; letter-spacing: 3px; }
  .pill { padding: 3px 8px; border: 1px solid var(--border); font-size: 11px; color: var(--muted); }
  .pill.on { color: var(--olive); }
  .meta { margin-left: auto; color: var(--muted); font-size: 11px; }
  #log { flex: 1; overflow-y: auto; padding: 12px 16px; }
  .line { display: flex; gap: 10px; line-height: 1.55; white-space: pre-wrap; word-break: break-all; }
  .idx { color: #3a4a2a; width: 56px; text-align: right; flex-shrink: 0; }
  .gap { color: var(--warn); font-style: italic; margin: 4px 0; }
  footer { padding: 8px 16px; border-top: 1px solid var(--border); color: var(--muted); font-size: 11px; }
</style>
</head>
<body>
  <header>
    <h1>SCARECROW // FLIGHT SCRIPT LOG</h1>
    <span id="state" class="pill">IDLE</span>
    <span id="flight" class="pill"></span>
    <span class="meta" id="meta">lines: 0</span>
  </header>
  <div id="log"></div>
  <footer><label><input type="checkbox" id="follow" checked> AUTOSCROLL</label></footer>
<script>
  const apiBase = window.location.origin || 'http://127.0.0.1:8000';
  let cursor = 0;
  const logEl = document.getElementById('log');
  const stateEl = document.getElementById('state');
  const flightEl = document.getElementById('flight');
  const metaEl = document.getElementById('meta');
  const followEl = document.getElementById('follow');
  function append(line, absIdx) {
    const row = document.createElement('div'); row.className = 'line';
    const idx = document.createElement('span'); idx.className = 'idx';
    idx.textContent = String(absIdx).padStart(5, '0');
    const body = document.createElement('span'); body.textContent = line;
    row.appendChild(idx); row.appendChild(body); logEl.appendChild(row);
  }
  function appendGap(n) {
    const row = document.createElement('div'); row.className = 'gap';
    row.textContent = '... ' + n + ' line(s) dropped ...'; logEl.appendChild(row);
  }
  async function tick() {
    try {
      const res = await fetch(apiBase + '/api/flight/log?since=' + cursor);
      const data = await res.json();
      if (data.dropped > 0) appendGap(data.dropped);
      let idx = data.start;
      for (const line of data.lines) { append(line, idx); idx += 1; }
      cursor = data.cursor;
      stateEl.textContent = data.running ? 'RUNNING' : 'IDLE';
      stateEl.className = 'pill ' + (data.running ? 'on' : '');
      flightEl.textContent = data.flight_id ? ('FLIGHT: ' + data.flight_id) : '';
      metaEl.textContent = 'lines: ' + cursor;
      if (followEl.checked) logEl.scrollTop = logEl.scrollHeight;
    } catch (e) { stateEl.textContent = 'OFFLINE'; }
  }
  tick(); setInterval(tick, 1000);
</script>
</body>
</html>
"""


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
        "mapPath": flight.map_path,
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
