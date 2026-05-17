# models

Gazebo SDF simulation models for drone, sensors, and test targets. `launch.sh` keeps this repository as the source of truth and exposes these models to PX4/Gazebo through a clean symlink mirror under `px4/build/scarecrow_gz_models/`.

## Subdirectories
- `ceiling_net/` — Static chain-link ceiling mesh used by `worlds/hangar_1.sdf`. Contains `model.sdf`, `model.config`, and `meshes/ceiling_net.glb`.
- `holybro_x500/` — Holybro X500 quadcopter frame with all sensors attached (optical flow, rangefinder, 2D lidar, mono camera). model.sdf defines the full drone including sensor plugins.
- `lidar_2d_v2/` — 2D scanning lidar sensor plugin (1440 samples, 360 degrees, ~10Hz). Simulates RPLidar A1M8.
- `mono_cam/` — Mono camera sensor plugin. Currently configured for 1280x720 capture to improve pigeon visibility while keeping the sim stable enough for flight tests. Topic: `camera_link/sensor/camera/image`.
- `mono_cam_hd/` — Fixed monitoring camera model for GUI replacement stream. Configured at 1280x720 with `update_rate=30`. Intended for observer stream only (not flight/detection pipeline input).
- `military_drone/` — Alternative drone model for visual variety in testing
- `pigeon_billboard/` — Visual billboard target with pigeon image. Used in drone_garage world for YOLO detection testing. Placed 5m in front of spawn.
- `pigeon_3d/` — 3D pigeon target model used by the alternate garage world for more realistic detection testing.
- `yolo/` — YOLOv8 trained model weights: `best_v4.pt` (pigeon detection, trained on custom dataset)
