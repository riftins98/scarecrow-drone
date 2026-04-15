# flight

Python scripts for autonomous flight missions. Run with `.venv-mavsdk` activated. Each script is self-contained: connects to MAVSDK, verifies sensors, arms, flies, and lands.

The webapp spawns these as subprocesses via DetectionService/DroneService and parses their stdout for status updates (DETECTION_IMAGE:, TELEMETRY:, etc.).

## Files
- `demo_flight.py` — Main detection flight: connect, verify GPS-denied params, takeoff to 2.5m, start lidar+camera+YOLO, stabilize at hover position, run detection for HOVER_DURATION seconds, land, build video. Accepts `--flight-id` for webapp integration. This is the script spawned by DetectionService.
- `room_circuit.py` — Navigate full room perimeter: 4-leg wall follow + 90-degree rotation at each corner. Uses WallFollowController + FrontWallDetector + rotate_90 + DistanceStabilizerController. Configurable: wall side, distance, speed, number of legs.
- `wall_follow.py` — Single-leg wall following mission: takeoff, stabilize, follow one wall until front wall detected, land.
- `detect_pigeons.py` — Standalone YOLO detection from Gazebo camera feed without flight. Saves annotated frames to output dir. Useful for testing detection without flying.
- `sensor_check.py` — Sensor diagnostics: checks lidar scan, compass heading, optical flow status. No flight.
