# sensors (unit tests)

Tests for `scarecrow/sensors/`. Gazebo-dependent subprocess code is stubbed.

## Files
- `__init__.py` — Package marker (empty).
- `test_lidar_scan.py` — `LidarScan` geometry: front/rear/left/right distances + SVD wall-angle error.
- `test_gazebo_lidar.py` — `GazeboLidar._discover_topic()` with a cached topic list (filters out `/points`).
- `test_gz_utils.py` — `prefetch_gz_env_async()` + `get_gz_env()` partition detection.
