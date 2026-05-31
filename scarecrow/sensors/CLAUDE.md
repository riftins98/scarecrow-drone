# sensors

Sensor interface abstractions for sim and hardware. Each sensor type has a base ABC and driver implementations for Gazebo (sim) and real hardware.

## Subdirectories
- `lidar/` — 2D lidar: LidarScan data class with geometry methods (distances, SVD wall alignment), GazeboLidar and RPLidar drivers (see `lidar/CLAUDE.md`)
- `camera/` — Camera abstractions: CameraFrame, CameraSource ABC, GazeboCamera driver (see `camera/CLAUDE.md`)
- `rangefinder/` — Single-ray rangefinder (e.g. upward ceiling clearance sensor): GazeboRangefinder driver (see `rangefinder/CLAUDE.md`)

## Files
- `__init__.py` — Re-exports single-ray rangefinder support (`GazeboRangefinder`, `RangefinderReading`) from the `rangefinder/` subpackage.
- `gz_entities.py` — Gazebo CLI/SDF entity helpers for discovering world/model names, parsing live model poses, mapping PX4 local XY into Gazebo world XY, and removing pursued target models from running worlds.
- `gz_utils.py` — Gazebo CLI helpers: `get_gz_env()` auto-detects env/partition; `prefetch_gz_env_async()` + `GzPrefetchResult` runs env detection + `gz topic -l` in a background thread so flight scripts can overlap ~2s of Gazebo setup with MAVSDK handshake
