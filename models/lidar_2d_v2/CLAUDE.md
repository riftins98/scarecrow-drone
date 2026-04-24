# lidar_2d_v2

2D scanning lidar sensor model (1440 samples over 360 degrees, ~10 Hz). Simulates an RPLidar A1M8.

## Files
- `model.sdf` — Sensor plugin definition: publishes `lidar_2d_v2/scan` (LaserScan) and `.../scan/points` (PointCloud). The `/scan` variant is what `GazeboLidar` consumes; `/points` is filtered out during topic discovery.
- `model.config` — Gazebo model manifest.

## Asset directories
- `meshes/` — `.dae` visual mesh + `.jpg` texture (pure assets).
- `thumbnails/` — Preview images for the Gazebo model library (pure assets).
