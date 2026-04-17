# lidar

Unified lidar interface for simulation and real hardware. All consumers work with LidarScan objects regardless of source.

## Files
- `__init__.py` — Exports LidarScan, LidarSource, GazeboLidar, RPLidar
- `base.py` — `LidarScan`: 360-degree range data (numpy arrays) with geometry methods: `front_distance()`, `rear_distance()`, `left_distance()`, `right_distance()`, `left_wall_angle_error()` (SVD), `right_wall_angle_error()` (SVD). `LidarSource` ABC with `start()`, `stop()`, `get_scan()`.
- `gazebo.py` — `GazeboLidar`: reads 2D lidar from Gazebo via `gz topic -e -n 1` CLI subprocess. Background thread polling with configurable num_threads for higher scan rate. `_discover_topic(topic_list=None)` auto-discovers the lidar_2d_v2/scan topic; accepts a cached topic list to avoid re-running `gz topic -l`; filters out the `/points` variant.
- `rplidar.py` — `RPLidar`: reads real RPLidar A1M8 via USB serial (`/dev/ttyUSB0`). Resamples variable-count scans to fixed 1440-sample format matching simulation.
