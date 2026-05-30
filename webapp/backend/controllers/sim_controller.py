"""Simulation lifecycle routes: /api/sim/*"""
import os
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dependencies import sim_service, detection_service, flight_service
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
    camera: Optional[str] = None  # e.g. "fixed", "center" — headless only


@router.post("/connect")
async def connect_sim(req: Optional[ConnectRequest] = None):
    """Launch PX4 + Gazebo (non-blocking, poll /api/sim/status for progress).

    Optional body:
        {"world": "drone_garage_pigeon_3d", "headless": false, "camera": "fixed"}
    Defaults match the legacy behavior (drone_garage_pigeon_3d, GUI).
    """
    try:
        world = (req.world if req else None) or "drone_garage_pigeon_3d"
        headless = bool(req.headless) if req else False
        camera = req.camera if req else None
        sim_service.launch(world=world, headless=headless, camera=camera)
        return {"success": True, "message": "Simulation launching..."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/connect")
async def disconnect_sim():
    sim_service.stop()
    return {"success": True}


class CameraSwitchRequest(BaseModel):
    camera: str  # "fixed" | "center"


@router.post("/camera")
async def switch_camera(req: CameraSwitchRequest):
    """Live-swap the headless stream to a different camera without
    restarting PX4/Gazebo. Returns {success, camera} or {success: False,
    error}. Frontend should show a brief 'switching…' state and let
    /api/sim/status reflect the new camera on the next poll.
    """
    return sim_service.switch_camera(req.camera)


@router.post("/reset")
async def reset_drone():
    """Panic reset: stop everything and snap the drone back to its spawn pose.

    Sequence (each step best-effort so a partial failure still resets the pose):
      1. Hard-kill the running flight script (it stops commanding the drone).
      2. Force-disarm via MAVSDK so the autopilot won't fly back up.
      3. Teleport the Gazebo model back to the spawn pose.
      4. Mark the in-progress flight aborted in the DB.

    Returns {success, killedFlight, disarmed, teleport, error?}.
    """
    if not sim_service.is_connected:
        return {"success": False, "error": "Simulation not running"}

    # The reset is several seconds of blocking work (pkill, MAVSDK disarm,
    # gz set_pose). Offload it to a worker thread so we don't stall the event
    # loop (and so force_disarm's own event loop has a thread without a running
    # loop to run on — calling it inline from this async handler would raise
    # "cannot be called from a running event loop").
    def _do_reset() -> dict:
        # 1. Kill the flight script (if any) so it stops sending setpoints.
        flight_id = detection_service.flight_id
        killed = detection_service.kill()

        # 2. Disarm via PX4's console (commander disarm -f) — instant and
        #    race-free, vs. opening a competing MAVLink connection. Exits
        #    offboard to Hold first so PX4 stops chasing its last setpoint.
        disarmed = sim_service.disarm_via_console()

        # 3. Teleport back to spawn.
        teleport = sim_service.reset_drone_pose()

        # 4. Mark the flight aborted so history reflects the panic stop.
        if flight_id:
            try:
                flight_service.abort_flight(flight_id)
            except Exception:
                pass

        return {
            "success": bool(teleport.get("success")),
            "killedFlight": killed,
            "disarmed": disarmed,
            "teleport": teleport,
            "error": teleport.get("error"),
        }

    import asyncio
    return await asyncio.to_thread(_do_reset)


@router.get("/status")
async def sim_status():
    return {
        "connected": sim_service.is_connected,
        "launching": sim_service.launching,
        "log": sim_service.get_log(20),
        "progress": sim_service.launch_progress,
        "world": sim_service.world,
        "headless": sim_service.headless,
        "camera": sim_service.camera,
        "streamUrl": sim_service.stream_url,
    }


@router.get("/log")
async def sim_log(since: int = 0):
    """Return sim launcher stdout lines with absolute index >= since.

    Polled by the frontend SystemLog to show real launcher output (PX4
    build, Gazebo start, etc.) during the launch checklist.
    """
    return sim_service.get_log_since(since=since)


@router.get("/log/view", response_class=HTMLResponse)
async def sim_log_view():
    """Standalone HTML page that tails the live sim launcher log.

    Opened by the SystemLog popout button. Polls /api/sim/log on a 1s
    interval, autoscrolls, dark monospace styling. Plain JS so it
    survives the React app reloading.
    """
    return _SIM_LOG_VIEW_HTML


_SIM_LOG_VIEW_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Scarecrow // Sim Launcher Log</title>
<style>
  :root {
    --bg: #0a0d08; --panel: #0d1208; --border: #2a3a1a;
    --text: #c0c0c0; --muted: #707070; --olive: #8b9a5b;
    --olive-bright: #d4e090; --teal: #7a9a9a; --warn: #d8a05a;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    height: 100%; background: var(--bg); color: var(--text);
    font-family: 'Consolas', 'Courier New', monospace; font-size: 13px;
  }
  body { display: flex; flex-direction: column; }
  header {
    display: flex; align-items: center; gap: 14px;
    padding: 10px 16px;
    background: linear-gradient(180deg, #1a1f15 0%, #0d1208 100%);
    border-bottom: 1px solid var(--border);
  }
  h1 {
    color: var(--olive); font-size: 13px; letter-spacing: 3px;
    font-weight: 700; text-shadow: 0 0 6px rgba(139,154,91,0.3);
  }
  .pill {
    padding: 3px 8px; border: 1px solid var(--border); border-radius: 1px;
    font-size: 11px; letter-spacing: 1.5px; color: var(--muted);
    background: var(--bg);
  }
  .pill.on  { color: var(--olive); border-color: #4a5a3a; box-shadow: 0 0 6px rgba(139,154,91,0.3); }
  .pill.off { color: #555; }
  .meta { margin-left: auto; color: var(--muted); font-size: 11px; letter-spacing: 1.5px; }
  #log { flex: 1; overflow-y: auto; padding: 12px 16px; background: var(--bg); }
  .line {
    display: flex; gap: 10px; line-height: 1.55;
    border-bottom: 1px dashed rgba(139,154,91,0.05);
    padding: 2px 0; white-space: pre-wrap; word-break: break-all;
  }
  .idx  { color: #3a4a2a; flex-shrink: 0; width: 56px; text-align: right; }
  .body { color: var(--text); flex: 1; }
  .gap {
    color: var(--warn); font-style: italic; padding: 4px 0;
    border-top: 1px solid rgba(216,160,90,0.3);
    border-bottom: 1px solid rgba(216,160,90,0.3); margin: 4px 0;
  }
  #log::-webkit-scrollbar { width: 6px; }
  #log::-webkit-scrollbar-track { background: var(--bg); }
  #log::-webkit-scrollbar-thumb { background: var(--border); }
  footer {
    display: flex; align-items: center; gap: 14px;
    padding: 8px 16px;
    background: linear-gradient(180deg, #0d1208 0%, #0a0d08 100%);
    border-top: 1px solid var(--border);
    color: var(--muted); font-size: 11px; letter-spacing: 1.5px;
  }
  label { display: flex; gap: 6px; align-items: center; cursor: pointer; user-select: none; }
  input[type=checkbox] { accent-color: var(--olive); }
</style>
</head>
<body>
  <header>
    <h1>SCARECROW // SIM LAUNCHER LOG</h1>
    <span id="state" class="pill off">IDLE</span>
    <span id="world" class="pill"></span>
    <span class="meta" id="meta">lines: 0</span>
  </header>
  <div id="log"></div>
  <footer>
    <label><input type="checkbox" id="follow" checked> AUTOSCROLL</label>
    <span class="meta" id="rate">poll: 1.0s</span>
  </footer>
<script>
  const apiBase = (window.location.origin || 'http://127.0.0.1:8000');
  let cursor = 0;
  const logEl = document.getElementById('log');
  const stateEl = document.getElementById('state');
  const worldEl = document.getElementById('world');
  const metaEl = document.getElementById('meta');
  const followEl = document.getElementById('follow');

  function append(line, absIdx) {
    const row = document.createElement('div');
    row.className = 'line';
    const idx = document.createElement('span');
    idx.className = 'idx';
    idx.textContent = String(absIdx).padStart(5, '0');
    const body = document.createElement('span');
    body.className = 'body';
    body.textContent = line;
    row.appendChild(idx); row.appendChild(body);
    logEl.appendChild(row);
  }
  function appendGap(n) {
    const row = document.createElement('div');
    row.className = 'gap';
    row.textContent = '... ' + n + ' line(s) dropped (buffer rolled) ...';
    logEl.appendChild(row);
  }
  async function tick() {
    try {
      const res = await fetch(apiBase + '/api/sim/log?since=' + cursor);
      const data = await res.json();
      if (data.dropped > 0) appendGap(data.dropped);
      let idx = data.start;
      for (const line of data.lines) { append(line, idx); idx += 1; }
      cursor = data.cursor;
      stateEl.textContent = data.running ? 'RUNNING' : 'IDLE';
      stateEl.className = 'pill ' + (data.running ? 'on' : 'off');
      worldEl.textContent = data.world ? ('WORLD: ' + data.world) : '';
      metaEl.textContent = 'lines: ' + cursor + '  buffer-start: ' + data.start;
      if (followEl.checked) logEl.scrollTop = logEl.scrollHeight;
    } catch (e) {
      stateEl.textContent = 'OFFLINE';
      stateEl.className = 'pill off';
    }
  }
  tick();
  setInterval(tick, 1000);
</script>
</body>
</html>
"""


@router.get("/options")
async def sim_options():
    """List available worlds + flight scripts (with parsed CLI args).

    Used by the frontend to render the pre-connect world/headless picker and
    the post-connect script picker.
    """
    fast_metadata = os.getenv("SCARECROW_FAST_SCRIPT_METADATA", "").lower() in ("1", "true", "yes")
    return {
        "worlds": [world_info_to_dict(w) for w in list_worlds(WORLDS_DIR)],
        "scripts": [script_info_to_dict(s) for s in list_flight_scripts(SCRIPTS_DIR, fast=fast_metadata)],
    }
