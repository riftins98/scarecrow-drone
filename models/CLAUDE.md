# models

Gazebo SDF simulation models for the drone, sensors, and test targets. Copied into `px4/Tools/simulation/gz/models/` by `scripts/shell/launch.sh` before each SITL build.

## Subdirectories
- `holybro_x500/` — Holybro X500 quadcopter frame with the full sensor stack attached (see `holybro_x500/CLAUDE.md`).
- `lidar_2d_v2/` — 2D scanning lidar sensor plugin, simulates RPLidar A1M8 (see `lidar_2d_v2/CLAUDE.md`).
- `mono_cam/` — Mono camera sensor plugin, ~Pi Camera 3 equivalent (see `mono_cam/CLAUDE.md`).
- `military_drone/` — Alternative visual-only drone model for scene variety (see `military_drone/CLAUDE.md`).
- `pigeon_billboard/` — Pigeon-image billboard used as a YOLO detection target (see `pigeon_billboard/CLAUDE.md`).
- `yolo/` — Trained YOLOv8 weights (asset dir, no code). Contains `best_v4.pt` (~22 MB, pigeon detection).
