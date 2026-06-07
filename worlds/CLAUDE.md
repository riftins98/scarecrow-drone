# worlds

Gazebo world SDF files defining simulation environments. `launch.sh` keeps these files repo-owned and exposes them to PX4/Gazebo through a deterministic symlink mirror under `px4/build/scarecrow_gz_worlds/`.

## Files
- `hangar_1_wall_pursuit.sdf` — Mission copy of hangar_1 for wall-follow/pursuit testing. Keeps the richer hangar geometry, enables visual-only landing-pad/drone props for camera visibility control, and includes multiple removable pigeon targets.
- `drone_hangar_light.sdf` — Same-size performance variant of `hangar_1_wall_pursuit.sdf`. Keeps the 24m x 15m arena and mission layout, but reduces render cost with 2m floor tiles, fewer non-shadow lights, and disabled shadows.
- `drone_hangar_small.sdf` — Smaller 16m x 10m drone hangar arena with reduced side-wall detail, fewer ceiling beams, 2m floor tiles, 2.4m/2.35m pads, and half-size parked drone props while keeping the active X500, pigeon targets, and cameras unscaled.
- `hangar_lite.sdf` — Lightweight 12m x 8m x 8m hangar shell with checkerboard floor tiles for optical flow, flat ceiling, plain perimeter walls, a transparent visual back wall that still has lidar collision, multiple `pigeon_3d` targets for repeated pursuit attempts, and fixed `mono_cam_hd` observer cameras. Layout is aligned for the hangar circuit pursuit mission; `launch_with_stream.sh hangar_lite` keeps the established stream-spawn position unless `PX4_GZ_MODEL_POSE` is set.
