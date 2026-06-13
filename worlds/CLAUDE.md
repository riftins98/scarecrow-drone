# worlds

Gazebo world SDF files defining simulation environments. `launch.sh` keeps these files repo-owned and exposes them to PX4/Gazebo through a deterministic symlink mirror under `px4/build/scarecrow_gz_worlds/`.

**Nothing is hardcoded in app code.** The backend scans `worlds/*.sdf` for the dropdown list, derives display labels from each filename (`hangar_small` → "Hangar Small"), and parses spawn geometry from the SDF for the spawn picker and default spawn pose. Optional env override: `SCARECROW_DEFAULT_WORLD=<id>`.

## Files

| SDF file | UI label (auto) | Notes |
|----------|-----------------|-------|
| `hangar.sdf` | Hangar | 24m × 15m performance hangar (2m floor tiles, reduced lighting/shadows). |
| `hangar_small.sdf` | Hangar Small | 16m × 10m compact hangar with corner pigeon shelves and half-size parked drone props. |
| `hangar_detailed.sdf` | Hangar Detailed | Full-detail 24m × 15m hangar with rich geometry, removable pigeon targets, visual landing-pad/drone props. |
| `hangar_lite.sdf` | Hangar Lite | Lightweight 12m × 8m shell for the capstone pursuit mission (checkerboard floor, multiple `pigeon_3d` targets). |

To add a world: drop `worlds/my_world.sdf` — it appears in the webapp and launch scripts automatically. Set `SCARECROW_DEFAULT_WORLD=my_world` in `env.sh` if it should be the session default.
