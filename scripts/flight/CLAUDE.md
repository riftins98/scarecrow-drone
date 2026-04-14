# flight

Python scripts for autonomous flight missions. Run with `.venv-mavsdk` activated.

## Files
- `wall_follow.py` — Full wall-following mission: takeoff, stabilize, follow left wall at 2m, stop at front wall, land
- `room_circuit.py` — Navigate room perimeter (multi-leg wall follow + rotation)
- `demo_flight.py` — Complete flight with YOLO pigeon detection, video recording, and webapp database integration
- `detect_pigeons.py` — Standalone YOLOv8 pigeon detection from Gazebo camera feed; saves annotated frames
- `sensor_check.py` — Sensor diagnostics (lidar, compass, optical flow)
