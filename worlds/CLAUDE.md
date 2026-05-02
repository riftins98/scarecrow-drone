# worlds

Gazebo world SDF files defining simulation environments. Copied into `px4/Tools/simulation/gz/worlds/` by `launch.sh`.

## Files
- `default.sdf` — PX4 default open world. Drone hovers stably here. Good for basic flight testing.
- `indoor_room.sdf` — Indoor room with walls, floor, and obstacles. Known issue: drone crashes after ~4s due to wall drift (no stable optical flow position hold in tight space). Needs larger room or better tuning.
- `drone_garage.sdf` — Garage environment (~20m) with pigeon billboard target at 5m in front of spawn. Benchmark world for detection + chase testing.
- `drone_garage_pigeon_3d.sdf` — Alternate garage world that swaps the billboard for the `pigeon_3d` model while keeping the same overall test area. Includes a static external fixed camera (`fixed_cam`, model `mono_cam_hd`) for headless monitoring stream.
