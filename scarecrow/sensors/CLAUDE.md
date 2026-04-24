# sensors

Sensor interface abstractions for sim and hardware. Each sensor type has a base ABC and driver implementations for Gazebo (sim) and real hardware.

## Subdirectories
- `lidar/` — 2D lidar: LidarScan data class with geometry methods (distances, SVD wall alignment), GazeboLidar and RPLidar drivers (see `lidar/CLAUDE.md`)
- `camera/` — Camera: CameraSource ABC, GazeboCamera driver with gz topic polling + PNG recording + ffmpeg video stitching (see `camera/CLAUDE.md`)

## Files
- `__init__.py` — Package init
- `gz_utils.py` — Gazebo CLI helpers: `get_gz_env()` auto-detects env/partition; `prefetch_gz_env_async()` + `GzPrefetchResult` runs env detection + `gz topic -l` in a background thread so flight scripts can overlap ~2s of Gazebo setup with MAVSDK handshake
