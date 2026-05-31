# worlds

Gazebo world SDF files defining simulation environments. `launch.sh` keeps these files repo-owned and exposes them to PX4/Gazebo through a deterministic symlink mirror under `px4/build/scarecrow_gz_worlds/`.

## Files
- `default.sdf` — PX4 default open world. Drone hovers stably here. Good for basic flight testing.
- `indoor_room.sdf` — Indoor room with walls, floor, and obstacles. Known issue: drone crashes after ~4s due to wall drift (no stable optical flow position hold in tight space). Needs larger room or better tuning.
- `drone_garage.sdf` — Garage environment (~20m) with pigeon billboard target at 5m in front of spawn. Benchmark world for detection + chase testing.
- `drone_garage_pigeon_3d.sdf` — Alternate garage world that swaps the billboard for the `pigeon_3d` model while keeping the same overall test area. Includes a static external fixed camera (`fixed_cam`, model `mono_cam_hd`) for headless monitoring stream.
- `hangar_1.sdf` — Large 24m x 15m x 8m indoor hangar world with checkerboard floor, landing pads, gray metal perimeter walls, a visual-only framed/louver band on the long east wall, a closed ceiling sheet for upward lidar hits, straight ceiling beams for a 6-by-3 grid, roof panels, debris, lights, military drone props, pigeon target, and fixed `mono_cam_hd` observer cameras. Diagonal X-bracing is disabled for flight stability.
- `hangar_lite.sdf` — Lightweight 12m x 8m x 8m hangar shell with checkerboard floor tiles for optical flow, flat ceiling, plain perimeter walls, a transparent visual back wall that still has lidar collision, one `pigeon_3d` target, and fixed `mono_cam_hd` observer cameras. Layout is aligned for the hangar circuit pursuit mission; `launch_with_stream.sh hangar_lite` defaults the drone spawn to a 3m-by-3m wall-follow start unless `PX4_GZ_MODEL_POSE` is set.
