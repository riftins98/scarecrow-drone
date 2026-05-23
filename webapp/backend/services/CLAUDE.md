# services

Business logic layer. Services coordinate repositories and external resources (subprocesses). Two categories of service live here:

- **Subprocess services** (sim_service, detection_service): manage long-running external processes. Stateful — hold PID, running flag, parsed stdout. Not easily unit-tested.
- **Business services** (flight, drone, area_map, chase_event, telemetry, recording): pure orchestration over repositories. Fully unit-testable.

## Files
- `__init__.py` — Re-exports all services for `from services import *`
- `sim_service.py` — `SimService`: manages PX4+Gazebo lifecycle. `launch(world, headless)` spawns the bash launcher (`launch.sh` for GUI or `launch_with_stream.sh --headless`) as a subprocess. Tracks the 11-stage launch progress, captures the stream URL from the headless banner, kills `gz sim` / `px4` / `stream_camera` processes on `stop()`. Exposes `world`, `headless`, `stream_url` as read-only properties.
- `detection_service.py` — `DetectionService`: spawns a chosen script in `scripts/flight/` as a subprocess. `start(flight_id, on_detection, script_name="demo_flight_v2.py", script_args={})`: validates the script exists under scripts/flight/, formats the dict into argparse-style `--flag value` CLI tokens (bool True -> bare flag, bool False / None / "" -> skipped), and always appends `--flight-id` unless the user already supplied it. Background thread parses stdout protocol: `DETECTION_IMAGE:` (tracks image path + triggers on_detection callback), `TELEMETRY:{json}`, `VIDEO_PATH:`. `stop()` detaches rather than kills -- the flight script handles its own landing.
- `script_metadata.py` — Introspects flight scripts and worlds for the webapp's pre-flight pickers. `list_worlds(worlds_dir)` enumerates `*.sdf`. `list_flight_scripts(scripts_dir)` runs `python3 <script> --help` (subprocess, never imports the script — flight scripts have heavy side effects) and parses argparse output into typed `ScriptArg` records (str/int/float/bool/choice). Scripts that don't use argparse or have heavy import-time logic time out cleanly; the resulting ScriptInfo carries a `parse_error` and the UI falls back to "no parameters."
- `flight_service.py` — `FlightService`: flight lifecycle (create_flight, start_detection, stop_flight, abort_flight, get_flight_summary, delete_flight). Coordinates FlightRepository + TelemetryRepository + DetectionService.
- `drone_service.py` — `DroneService`: wraps DetectionService with drone-specific API (get_status, start_flight, stop_flight, abort, return_home, get_telemetry). Phase 6 (UC7) will extend with SIGTERM handling.
- `area_map_service.py` — `AreaMapService`: CRUD for area maps + mapping session state (start_mapping is stubbed for Phase 3 UC1).
- `chase_event_service.py` — `ChaseEventService`: chase event lifecycle for UC5. Validates counter_measure_type (pursuit/movement/combined) and outcome (dispersed/lost/aborted).
- `telemetry_service.py` — `TelemetryService`: per-flight telemetry tracking (battery, distance, detection count). 1:1 with flights.
- `recording_service.py` — `RecordingService`: video recording status for UC3. The actual PNG+ffmpeg pipeline lives in GazeboCamera; this service just tracks recording state for the webapp.

## Subprocess stdout protocol
Flight scripts communicate with services via stdout lines parsed by the monitoring thread:
- `DETECTION_IMAGE:/path/to/img.png` — parsed by DetectionService (implemented)
- Future (Phase 4-6): `TELEMETRY:{json}`, `CHASE_START:type`, `CHASE_END:outcome`, `MAP_RESULT:{json}`, `ABORT_REQUESTED`
