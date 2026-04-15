# services

Backend service layer for simulation lifecycle and detection management.

## Files
- `sim_service.py` — `SimService`: manages PX4+Gazebo lifecycle. `launch()` spawns PX4 SITL build as subprocess, tracks 11-stage launch progress (clean, copy models, build, launch, etc.), `stop()` kills process tree. Properties: `is_connected`, `launching`, `launch_progress`, `get_log()`.
- `detection_service.py` — `DetectionService`: spawns `scripts/flight/demo_flight.py` as subprocess with `--flight-id`. Background thread monitors stdout, parses `DETECTION_IMAGE:` lines for image paths, tracks pigeons_detected and frames_processed counts. `start(flight_id, on_detection)` begins, `stop()` detaches (does NOT kill — flight script handles its own landing). This subprocess pattern is reused for all flight types.

## Subprocess stdout protocol
Flight scripts communicate with services via stdout lines:
- `DETECTION_IMAGE:/path/to/img.png` — parsed by DetectionService
- Future: `TELEMETRY:{json}`, `CHASE_START:type`, `CHASE_END:outcome`, `MAP_RESULT:{json}`
