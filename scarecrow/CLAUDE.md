# scarecrow

Python package for drone flight controllers, sensor interfaces, detection, and navigation. Designed to run identically on simulation (Gazebo) and real hardware (Raspberry Pi 5).

## Subdirectories
- `controllers/` — GPS-denied flight control algorithms: wall follow (PD+SVD), rotation (compass+lidar), distance stabilization, front wall detection, target pursuit (see `controllers/CLAUDE.md`)
- `sensors/` — Sensor abstractions for lidar and camera, both sim and hardware drivers (see `sensors/CLAUDE.md`)
- `detection/` — YOLOv8 pigeon detection (see `detection/CLAUDE.md`)
- `flight/` — Async MAVSDK helpers + Flight orchestrator (see `flight/CLAUDE.md`)
- `navigation/` — NavigationUnit and MapUnit domain classes (see `navigation/CLAUDE.md`)

## Files
- `__init__.py` — Package init
- `drone.py` — Drone class wrapping MAVSDK: connect, arm (with retries + already-armed kill recovery), disarm (with action.kill fallback), takeoff (split into prepare_takeoff pre-arm + takeoff post-arm), offboard control, telemetry, verify_gps_denied_params, set_ekf_origin, emergency_land. Honors `MAVSDK_SERVER_ADDRESS` / `MAVSDK_SERVER_PORT` env vars to connect to an externally-launched `mavsdk_server` (used for debugging server crashes).
- `logging_setup.py` — Structured logger factory: `get_logger(name, run_id, prefix)` returns a logger that writes JSON-ish event lines to `output/logs/<prefix>_<timestamp>Z.log` and stderr. Helpers: `log_event(logger, event, **fields)`, `Timer(logger, "label", **fields)` context manager, `log_run_file_path()`.
