# lidar

Unified lidar interface for simulation and real hardware. All consumers work with LidarScan objects regardless of source.

## Files
- `__init__.py` — Exports LidarScan, LidarSource, GazeboLidar, RPLidar
- `base.py` — `LidarScan`: 360-degree range data (numpy arrays) with geometry methods: `front_distance()`, `rear_distance()`, `left_distance()`, `right_distance()`, `left_wall_angle_error()` (SVD), `right_wall_angle_error()` (SVD). `LidarSource` ABC with `start()`, `stop()`, `get_scan()`.
- `gazebo.py` — `GazeboLidar`: reads 2D lidar from Gazebo. Prefers an in-process `gz.transport13` subscription (~30 Hz, no subprocesses); falls back to `gz topic -e -n 1` background-thread polling (~6 Hz) when the bindings are missing. `num_threads` applies to the fallback only. `_build_scan()` holds the validation both paths share, so the 360-degree contract cannot differ by read path. `_discover_topic(topic_list=None)` auto-discovers the lidar_2d_v2/scan topic; accepts a cached topic list to avoid re-running `gz topic -l`; filters out the `/points` variant.
- `rplidar.py` — `RPLidar`: reads real RPLidar A1M8 via USB serial (`/dev/ttyUSB0`). Resamples variable-count scans to fixed 1440-sample format matching simulation.
