# models

Gazebo SDF simulation models for drone, sensors, and test targets. `launch.sh` keeps this repository as the source of truth and exposes these models to PX4/Gazebo through a clean symlink mirror under `px4/build/scarecrow_gz_models/`.

## Subdirectories
- `ceiling_net/` — Static chain-link ceiling mesh used by `worlds/hangar_1.sdf`. Contains `model.sdf`, `model.config`, and `meshes/ceiling_net.glb`.
- `holybro_x500/` — Holybro X500 quadcopter frame with all sensors attached (optical flow, downward rangefinder, upward ceiling rangefinder, 2D lidar, mono camera). model.sdf defines the full drone including sensor plugins and keeps the flight sensors close to the frame so lidar/camera/rangefinder origins match the EKF sensor-offset configuration.
- `drone_view_cam/` — Collisionless camera sensor used only by `launch_with_stream.sh --drone_view`. The launcher injects it into a temporary `holybro_x500` overlay as a fixed link 1.5m behind and 0.5m above `base_link`, pitched 10 degrees downward, so it can clip through geometry without collision effects. Profile is 1280x720 at 15 Hz sim-time, matching `mono_cam_hd`. 15 Hz delivers ~10 Hz wall-clock at current RTF, which is what the streamer consumes -- rendering faster only produces frames that get discarded. Sharpness comes from resolution and encoder quality, not from update rate.
- `lidar_2d_v2/` — 2D scanning lidar sensor plugin (1440 samples, 360 degrees, `update_rate=50` sim-time). Simulates an RPLidar A1M8 -- **but the real A1M8 spins at roughly 5.5 Hz**, so the sim delivers several times more scans than the hardware will. Controllers tuned against sim rates will track more loosely on the drone; the rate-dependent constants are fixed, so it degrades rather than misbehaves.
- `mono_cam/` — Mono camera sensor plugin. Currently configured for 1280x720 capture to improve pigeon visibility while keeping the sim stable enough for flight tests. Topic: `camera_link/sensor/camera/image`.
- `mono_cam_hd/` — Fixed monitoring camera model for GUI replacement stream. Configured at 1280x720 with `update_rate=15` (see `drone_view_cam` for why 15). Intended for observer stream only (not flight/detection pipeline input).
- `military_drone/` — Alternative drone model for visual variety in testing
- `military_drone_half/` — Half-size visual/collision variant of `military_drone`, used by smaller hangar pursuit worlds to keep parked drone props visible while reducing their footprint.
- `pigeon_billboard/` — Visual billboard target with pigeon image. Used in drone_garage world for YOLO detection testing. Placed 5m in front of spawn.
- `pigeon_3d/` — 3D pigeon target model used by the alternate garage world for more realistic detection testing.
- `tf_luna_up/` — Upward-facing TF-Luna-style single-ray rangefinder for ceiling clearance in roofed indoor worlds. Topic: `tf_luna_up_link/sensor/ceiling_rangefinder/scan`.
- `yolo/` — YOLO model weights used by flight scripts: `best_v4.pt` (custom pigeon detector) and `yolov8s.pt` (general YOLOv8 small model used by the current hangar pursuit script with class filtering).
