# flight

Python scripts for autonomous flight missions. Run with `.venv-mavsdk` activated. Each script is self-contained: connects to MAVSDK, verifies sensors, arms, flies, and lands.

The webapp spawns these as subprocesses via DetectionService and parses their stdout for status updates. Stdout protocol lines recognized:
- `DETECTION_IMAGE:/path/to/img.png` — saved detection frame
- `TELEMETRY:{"battery":N,"distance":N,"detections":N}` — periodic state update
- `VIDEO_PATH:/path/to/flight_camera.mp4` — video built after landing

## Files
- `demo_flight_v2.py` — **Currently spawned by the webapp.** Uses the OO layer (Drone + NavigationUnit + preload_async + prefetch_gz_env_async). Does NOT touch the DB directly -- emits stdout protocol for the webapp to parse. Accepts optional `--flight-id` (auto-generates local ID if omitted). Explicitly binds YOLO camera input to the drone model topic (`/model/holybro_x500.../camera/image`) and aborts if only fixed monitor camera is found.
- `demo_flight.py` — Legacy v1 flight script. Kept as fallback. Same mission procedurally and writes to DB directly (layer violation). Also constrained to drone camera topic only (never fixed monitor camera). Change `webapp/backend/services/detection_service.py` path to revert to this script.
- `room_circuit.py` — Navigate full room perimeter: 4-leg wall follow + 90-degree rotation at each corner. Uses WallFollowController + FrontWallDetector + rotate_90 + DistanceStabilizerController.
- `room_circuit_v2.py` — Continuous wall-follow circuit with faster constant speed, 4-leg loop, and `Drone` helper flow. Supports Ctrl+C emergency landing via `Drone.emergency_land()`.
- `room_circuit_map.py` — Mapping flight: runs a 4-leg circuit, records lidar-based MapUnit samples, writes JSON map under `scarecrow/mapped_env/<datetime>/map.json`, emits `MAP_RESULT:`.
- `wall_follow.py` — Legacy single-leg wall-following mission using direct MAVSDK System calls.
- `wall_follow_v2.py` — Wall-follow v2: world-agnostic, uses `Drone` + `GazeboLidar` + `FrontWallDetector`, configurable side/target distance/speed/stop distance.
- `detect_pigeons.py` — Standalone YOLO detection from Gazebo camera feed without flight. Topic discovery is constrained to drone camera (`holybro_x500`) so monitoring cameras do not contaminate detection tests.
- `demo_flight_pursuit.py` — **Pigeon pursuit flight.** Extends `demo_flight_v2.py`: hovers with YOLO, on first pigeon detection transitions to pursuit (yaw-align + forward approach with center-band hysteresis), runs a bounded search sweep on target loss (`+25°` right then `50°` left), exits pursuit if not re-acquired, returns toward takeoff N/E before landing, then performs safer lidar-assisted descent (reduced/disabled XY correction near ground). Uses `_on_detection_data` callback for real-time detection metadata.
- `ceiling_clearance_flight.py` — Upward rangefinder flight test for roofed worlds: takeoff to 2.5m AGL, lidar-stabilize, climb until the ceiling sensor reads 1.5m clearance, hover, descend until the ceiling sensor reads 2.5m clearance, hover, then lidar-assisted land. Defaults to a 60s climb timeout and logs ceiling clearance continuously during climb/hover/descent/landing.
- `sensor_check.py` — Sensor diagnostics: checks lidar scan, compass heading, optical flow status. No flight.
- `check_ceiling_rangefinder.py` — Live Gazebo diagnostic for the upward TF-Luna-style ceiling rangefinder. Auto-discovers `tf_luna_up_link/sensor/ceiling_rangefinder/scan`, prints clearance samples, and exits non-zero if clearance drops below `--min-clearance`.
