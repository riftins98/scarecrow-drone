# flight

Python scripts for autonomous flight missions. Run with `.venv-mavsdk` activated. Each script is self-contained: connects to MAVSDK, verifies sensors, arms, flies, and lands.

The webapp spawns these as subprocesses via DetectionService and parses their stdout for status updates. Stdout protocol lines recognized:
- `DETECTION_IMAGE:/path/to/img.png` — saved detection frame
- `TELEMETRY:{"battery":N,"distance":N,"detections":N}` — periodic state update
- `VIDEO_PATH:/path/to/flight_camera.mp4` — video built after landing

## Files
- `demo_flight_v2.py` — **Currently spawned by the webapp.** Uses the OO layer (Drone + NavigationUnit + preload_async + prefetch_gz_env_async). Does NOT touch the DB directly -- emits stdout protocol for the webapp to parse. Accepts `--flight-id` from webapp, logs YOLO preload status before flight, and aborts early if the model is not ready.
- `demo_flight.py` — Legacy v1 flight script. Kept as fallback. Does the same mission procedurally and writes to DB directly (layer violation). Change the path in `webapp/backend/services/detection_service.py` to revert to this.
- `room_circuit.py` — Navigate full room perimeter: 4-leg wall follow + 90-degree rotation at each corner. Uses WallFollowController + FrontWallDetector + rotate_90 + DistanceStabilizerController.
- `wall_follow.py` — Single-leg wall following mission: takeoff, stabilize, follow one wall until front wall detected, land.
- `detect_pigeons.py` — Standalone YOLO detection from Gazebo camera feed without flight. Saves annotated frames to output dir. Useful for testing detection without flying.
- `sensor_check.py` — Sensor diagnostics: checks lidar scan, compass heading, optical flow status. No flight.
