# lidar

Unified lidar interface for simulation and real hardware.

## Files
- `__init__.py` — Exports LidarScan, LidarSource, GazeboLidar, RPLidar
- `base.py` — `LidarScan` (360° range data with geometry methods: distances, SVD wall alignment, tilt) and `LidarSource` ABC
- `gazebo.py` — `GazeboLidar`: reads 2D lidar from Gazebo via `gz topic` CLI; background thread polling
- `rplidar.py` — `RPLidar`: reads real RPLidar A1M8 via USB serial; resamples to fixed 1440-sample format
