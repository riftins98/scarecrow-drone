# scarecrow

Python package for drone flight controllers, sensor interfaces, detection, and navigation. Designed to run identically on simulation (Gazebo) and real hardware (Raspberry Pi 5).

## Subdirectories
- `controllers/` — GPS-denied flight control algorithms: wall follow (PD+SVD), rotation (compass+lidar), distance stabilization, front wall detection (see `controllers/CLAUDE.md`)
- `sensors/` — Sensor abstractions for lidar and camera, both sim and hardware drivers (see `sensors/CLAUDE.md`)
- `detection/` — YOLOv8 pigeon detection: `yolo.py` has YoloDetector with rate-limited inference, callbacks, and `preload_async()` for parallel model loading during MAVSDK connect
- `flight/` — Async MAVSDK helpers + Flight orchestrator (see `flight/CLAUDE.md`)
- `navigation/` — NavigationUnit and MapUnit domain classes (see `navigation/CLAUDE.md`)

## Files
- `__init__.py` — Package init
- `drone.py` — Drone class wrapping MAVSDK: connect, arm (with retries + already-armed kill recovery), disarm (with action.kill fallback), takeoff (split into prepare_takeoff pre-arm + takeoff post-arm), offboard control, telemetry, verify_gps_denied_params, set_ekf_origin
