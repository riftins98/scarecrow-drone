# unit

Unit tests mirroring the source tree. External dependencies (MAVSDK, YOLO, Gazebo subprocesses) are mocked. Runs in under 2 seconds.

## Subdirectories
- `scarecrow/` — Tests for the `scarecrow` Python package (controllers, drone, flight, navigation, sensors, detection).
- `webapp/` — Tests for the backend business services and repositories.

## Files
- `__init__.py` — Package marker (empty).
