# scarecrow (unit tests)

Unit tests for the `scarecrow` Python package. Layout mirrors `scarecrow/` itself.

## Subdirectories
- `controllers/` — WallFollow, DistanceStabilizer, FrontWallDetector controller tests.
- `detection/` — YoloDetector tests (rate limiting, callback, preload_async).
- `drone/` — Drone class tests with mocked `mavsdk.System`.
- `flight/` — Flight orchestrator tests.
- `navigation/` — NavigationUnit + MapUnit tests.
- `sensors/` — LidarScan geometry, GazeboLidar topic discovery, gz_utils prefetch tests.

## Files
- `__init__.py` — Package marker (empty).
