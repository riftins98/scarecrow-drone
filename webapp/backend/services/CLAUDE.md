# services

Backend service layer for simulation lifecycle and detection management.

## Files
- `sim_service.py` — Manages Gazebo/PX4 lifecycle: launch, track stages, shutdown
- `detection_service.py` — Spawns YOLO detection subprocess, parses output, triggers callbacks on detections
