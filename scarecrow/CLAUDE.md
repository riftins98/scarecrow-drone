# scarecrow

Python package for drone flight controllers, sensor interfaces, detection, and navigation. Designed to run identically on simulation (Gazebo) and real hardware (Raspberry Pi 5).

## Subdirectories
- `controllers/` — GPS-denied flight control algorithms: wall follow (PD+SVD), rotation (compass+lidar), distance stabilization, front wall detection (see `controllers/CLAUDE.md`)
- `sensors/` — Sensor abstractions for lidar and camera, both sim and hardware drivers (see `sensors/CLAUDE.md`)
- `detection/` — YOLOv8 pigeon detection with rate-limited inference and callbacks
- `flight/` — Async MAVSDK flight helpers: altitude wait, stability check, lidar-based position hold
- `navigation/` — NavigationUnit and MapUnit classes (currently `__init__.py` only — built in Phase 2)

## Files
- `__init__.py` — Package init
