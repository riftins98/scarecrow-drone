# controllers

Flight control algorithms for GPS-denied indoor navigation.

## Files
- `__init__.py` — Exports all controllers
- `wall_follow.py` — PD controller maintaining target distance from wall; outputs body-frame velocity with SVD-based yaw correction
- `rotation.py` — Precise 90° rotation using compass (coarse) + lidar SVD wall alignment (fine)
- `distance_stabilizer.py` — Multi-constraint hover positioning using lidar distances (front/rear/left/right targets)
- `front_wall_detector.py` — Robust front obstacle detection with clustering and temporal confirmation to prevent false stops
