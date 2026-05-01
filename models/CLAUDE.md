# models

Gazebo SDF simulation models for drone, sensors, and test targets. These are copied into `px4/Tools/simulation/gz/models/` by `launch.sh` before each build.

## Subdirectories
- `holybro_x500/` — Holybro X500 quadcopter frame with all sensors attached (optical flow, rangefinder, 2D lidar, mono camera). model.sdf defines the full drone including sensor plugins.
- `lidar_2d_v2/` — 2D scanning lidar sensor plugin (1440 samples, 360 degrees, ~10Hz). Simulates RPLidar A1M8.
- `mono_cam/` — Mono camera sensor plugin. Currently configured for 1280x720 capture to improve pigeon visibility while keeping the sim stable enough for flight tests. Topic: `camera_link/sensor/camera/image`.
- `mono_cam_hd/` — Fixed monitoring camera model for GUI replacement stream. Configured at 1280x720 with `update_rate=30`. Intended for observer stream only (not flight/detection pipeline input).
- `military_drone/` — Alternative drone model for visual variety in testing
- `pigeon_billboard/` — Visual billboard target with pigeon image. Used in drone_garage world for YOLO detection testing. Placed 5m in front of spawn.
- `pigeon_3d/` — 3D pigeon target model used by the alternate garage world for more realistic detection testing.
- `yolo/` — YOLOv8 trained model weights: `best_v4.pt` (pigeon detection, trained on custom dataset)
