# worlds

Gazebo world SDF files for Scarecrow Drone simulation. `launch.sh` symlinks these into `px4/build/scarecrow_gz_worlds/` for PX4/Gazebo.

Worlds are discovered automatically from `worlds/*.sdf`. The webapp dropdown label is derived from the filename (`hangar_small` → **Hangar Small**). Default session world: **`hangar_lite`** (`SCARECROW_DEFAULT_WORLD` in `env.sh`).

---

## Quick comparison

| ID (launch arg) | UI label | Floor | Ceiling | Shadows | Parked aircraft | Pigeon targets | Stream cameras |
|-----------------|----------|-------|---------|---------|-----------------|----------------|----------------|
| `hangar_lite` | Hangar Lite | 12 × 8 m | ~8 m flat sheet | Off | No | 2 × `pigeon_3d` | fixed, center |
| `hangar_small` | Hangar Small | 16 × 10 m | Beams + collision sheet | Off | 2 (half-scale) | 2 × `pigeon_3d` | fixed, center |
| `hangar` | Hangar | 24 × 15 m | Beams + collision sheet | Off | 2 (RQ-7B props) | 2 × `pigeon_3d` | fixed, center |
| `hangar_detailed` | Hangar Detailed | 24 × 15 m | Full beam grid + debris | **On** | 2 (visual pads/drones) | 2 × `pigeon_3d` | fixed, center |

All worlds include the active **Holybro X500** drone (with lidar, downward camera, upward ceiling rangefinder) spawned by PX4 at launch.

---

## Hangar Lite (`hangar_lite.sdf`) — **default**

**Purpose:** Capstone deterrence mission (`hangar_circuit_pursuit.py`), webapp patrol demo, and general GPS-denied indoor testing in a small arena.

**Layout:** Lightweight 12 m × 8 m × 8 m shell — plain perimeter walls, flat ceiling collision for upward lidar/rangefinder, 1 m checkerboard floor tiles (good optical-flow texture). South wall is visually transparent but still has lidar collision. No parked aircraft obstacles in the spawn map.

**Targets:** Two `pigeon_3d` models (north wall and east/south corner) for YOLO detection and pursuit; removable at runtime by the mission script.

**Lighting:** Scene ambient only + two non-shadow point lights. Shadows disabled for performance.

**Cameras:** `fixed_cam` (external overview from south), `center_cam` (overhead). Headless stream flags: `--fixed`, `--center`, plus `--drone_cam` / `--drone_view` on the live drone.

**Spawn:** Webapp spawn picker supported. Mission-tuned spawn for circuit start alignment: `PX4_GZ_MODEL_POSE=4,-3,0,0,0,0`. Auto-computed default (first clear floor corner) may differ — use the tuned pose for reliable start-corner stabilization.

**When to use:** Patrol mission, demos, WSL headless streaming, fastest iteration in a hangar-like space.

---

## Hangar Small (`hangar_small.sdf`)

**Purpose:** Mid-size hangar for testing wall-follow, pursuit, and navigation in a tighter space than the full 24 m arena, with lower render cost than Hangar Detailed.

**Layout:** 16 m × 10 m floor, simplified side-wall detail, reduced ceiling beam grid, 2 m floor tiles, brighter wall/frame materials. Corner pigeon shelves (visual). Half-scale parked RQ-7B drone props (`shadow_1`, `shadow_2`) block spawn in the center — spawn picker avoids them.

**Targets:** Two `pigeon_3d` models.

**Lighting:** Two non-shadow point lights. Shadows off.

**Cameras:** `fixed_cam`, `center_cam`.

**Spawn:** Supported (with aircraft obstacle footprints). Auto default from floor geometry.

**When to use:** Testing in a compact hangar without full 24 m geometry; good balance of realism and RTF.

---

## Hangar (`hangar.sdf`)

**Purpose:** Full-size (24 m × 15 m) mission layout optimized for **simulation performance** — same overall arena as Hangar Detailed but stripped for higher real-time factor.

**Layout:** 24 m × 15 m checkerboard floor (2 m tiles), ceiling beam grid + lightweight collision ceiling sheet, ceiling debris visuals, perimeter walls. Two full parked-aircraft footprints (`shadow_1`, `shadow_2`) in the center block custom spawn there.

**Targets:** Two `pigeon_3d` models.

**Lighting:** Two non-shadow fill lights. Shadows off, fewer lights than Hangar Detailed.

**Cameras:** `fixed_cam`, `center_cam`.

**Spawn:** Supported (aircraft obstacles). Tuned stream spawn historically: `-9,4.5,0,0,0,0`.

**When to use:** Full-size hangar missions when you need 24 m scale but want better RTF than Hangar Detailed. Former name: `drone_hangar_light`.

---

## Hangar Detailed (`hangar_detailed.sdf`)

**Purpose:** Richest visual hangar — wall-follow/pursuit testing with full geometry, shadows, and landing-pad/drone visual props. Highest fidelity, lowest RTF.

**Layout:** 24 m × 15 m × 8 m — checkerboard floor, gray metal walls, framed/louver band on the long east wall, 6×3 ceiling beam grid, roof panels, ceiling debris, landing pads, military drone visual props. Diagonal X-bracing disabled for flight stability. Two parked-aircraft spawn obstacles (`shadow_1`, `shadow_2`).

**Targets:** Two `pigeon_3d` models (removable). Visual-only pad/drone props for camera visibility control.

**Lighting:** Six point lights with **shadows enabled**.

**Cameras:** `fixed_cam`, `center_cam`.

**Spawn:** Supported. Tuned stream spawn historically: `-9,4.5,0,0,0,0`.

**When to use:** Visual demos, GUI Gazebo sessions, or validating pursuit/wall-follow against the most detailed environment. Former name: `hangar_1_wall_pursuit`.

---

## Adding a world

1. Add `worlds/<id>.sdf` with `<world name="<id>">`.
2. It appears in the webapp world dropdown and `launch.sh` / `launch_with_stream.sh` automatically.
3. Optional: set `SCARECROW_DEFAULT_WORLD=<id>` in `scripts/shell/env.sh`.
4. Floor collision geometry enables the webapp spawn picker (via `world_geometry.py`).
