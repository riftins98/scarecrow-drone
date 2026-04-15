# sensors

Sensor interface abstractions for sim and hardware. Each sensor type has a base ABC and driver implementations for Gazebo (sim) and real hardware.

## Subdirectories
- `lidar/` — 2D lidar: LidarScan data class with geometry methods (distances, SVD wall alignment), GazeboLidar and RPLidar drivers (see `lidar/CLAUDE.md`)
- `camera/` — Camera: CameraSource ABC, GazeboCamera driver (gz topic polling, PNG recording, ffmpeg video stitching)

## Files
- `__init__.py` — Package init
- `gz_utils.py` — Gazebo environment detection: finds gz binary path, sets GZ_PARTITION for topic access
