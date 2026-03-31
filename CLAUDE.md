# Scarecrow Drone — Full Project Context

## Project Goal

University final project: simulate a Holybro X500 V2 drone with full sensor stack for GPS-denied indoor flight. The simulation replaces delayed hardware and must prove **all sensors work** to get project approval. If the simulation works, the same flight code runs on the real drone.

### Sensor Stack (must match real hardware)

| Sensor | Hardware | Gazebo Model | Purpose |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity estimation |
| Downward rangefinder | TF-Luna | `LW20` + `lidar_sensor_link` (gpu_lidar) | Height correction |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance / self-position |
| Mono camera | Pi Camera 3 | `mono_cam` (1280x720) | Visual awareness |

GPS is disabled. Height uses barometer (Pixhawk built-in) + rangefinder correction. Baro is kept enabled — the real Pixhawk has one.

---

## Repository Structure

```
scarecrow-drone/
├── airframes/
│   └── 4022_gz_holybro_x500       ← custom airframe (GPS disabled, stock defaults)
├── config/
│   └── server.config              ← Gazebo server plugins (Sensors + OpticalFlowSystem)
├── models/
│   ├── holybro_x500/model.sdf     ← composite model: x500 + all 4 sensors
│   └── mono_cam/model.sdf         ← camera at 1280x720 for HD video recording
├── worlds/
│   ├── default.sdf                ← open world with checkerboard floor
│   └── indoor_room.sdf            ← 20m room: colored walls, obstacles, full checkerboard floor
├── scripts/
│   ├── shell/
│   │   ├── launch.sh              ← one-command launcher (GUI or headless)
│   │   └── env.sh                 ← shared environment variables
│   └── flight/
│       ├── demo_flight.py         ← MAVSDK flight demo + HD video + sensor capture
│       └── sensor_check.py        ← ground-only sensor data capture (no flight)
├── px4/                           ← git submodule: riftins98/PX4-Autopilot branch `scarecrow`
└── .venv-mavsdk/                  ← Python venv with mavsdk package
```

**GitHub**: `riftins98/scarecrow-drone` (private)
**PX4 fork**: `riftins98/PX4-Autopilot`, branch `scarecrow`
**Airframe**: ID 4022, model name `holybro_x500`

---

## Airframe Parameters

The airframe `4022_gz_holybro_x500` is based on the stock `4021_gz_x500_flow` with minimal changes:

```sh
# GPS disabled — indoor flight
SYS_HAS_GPS 0, SIM_GPS_USED 0, EKF2_GPS_CTRL 0

# Allow arming without GPS
COM_ARM_WO_GPS 1, COM_RC_IN_MODE 1
NAV_DLL_ACT 0, NAV_RCL_ACT 0
```

Everything else is PX4 stock defaults. Barometer, magnetometer, IMU, EKF2 — all at defaults.

**Runtime commands** (set in `pxh>` before each flight):
```
commander set_ekf_origin 0 0 0
commander set_heading 0
```

**Critical rules**:
- Don't over-configure EKF2. Stock defaults work. Only disable GPS.
- **NEVER `param set` EKF2 params at runtime** — it resets the estimator and destroys optical flow fusion.
- The `set_ekf_origin` is automated by the flight script. Only `set_heading 0` needs manual entry.

---

## Launch

### One Command

```bash
./scripts/shell/launch.sh                    # GUI + indoor room (default)
./scripts/shell/launch.sh default            # GUI + open world
./scripts/shell/launch.sh default --headless # headless mode
```

The launch script:
1. Kills previous PX4/Gazebo sessions
2. Copies airframe, config, models, worlds to PX4 dirs
3. Builds PX4 (incremental, fast after first build)
4. Launches PX4 + Gazebo (PX4 manages Gazebo)

### After Launch

In `pxh>`:
```
commander set_heading 0
```

(`set_ekf_origin` is handled by the flight script automatically)

### Flight Demo

In a second terminal:
```bash
source .venv-mavsdk/bin/activate
python3 scripts/flight/demo_flight.py
```

The script:
1. Verifies GPS is disabled and sensors are publishing
2. Sets EKF origin via MAVSDK
3. Arms and takes off to 2.5m using PX4's built-in takeoff controller
4. Hovers with optical flow position hold
5. Records HD camera video (1280x720, multi-threaded capture, MP4 via ffmpeg)
6. Captures lidar scan + optical flow during hover
7. Lands using PX4's built-in land controller

### Output Files

Saved to `output/` (gitignored):
- `flight_camera.mp4` — HD camera video from flight (real-time speed)
- `lidar_scan.pdf` — 2D lidar top-down room scan
- `optical_flow.pdf` — flow quality chart
- `camera_ground.png` / `camera_flight.png` — camera snapshots

---

## Worlds

### default.sdf
Open flat world with 10x10 checkerboard floor. Drone flies stably here (no walls to crash into). Optical flow needs the textured floor for feature tracking.

### indoor_room.sdf
20m x 20m room with:
- **Red** wall (north), **Blue** wall (south), **Green** wall (east), **Yellow** wall (west)
- White cylinder pillar, orange L-shaped wall, purple wedge, teal box stack
- **Full 20m x 20m checkerboard floor** (400 tiles, 1m each, wall-to-wall) for optical flow
- Obstacles placed 6-8m from center (clear hover zone)

---

## Files Changed from Upstream PX4

| File | Change |
|---|---|
| `ROMFS/.../4022_gz_holybro_x500` | Custom airframe: GPS disabled, arming overrides |
| `ROMFS/.../px4-rc.gzsim` | Added `sensors stop/start` after gz_bridge (EKF2 init race fix) |
| `src/.../GZMixingInterfaceESC.cpp` | float→double cast fix for Apple clang |
| `src/.../voted_sensors_update.cpp` | IMU priority auto-recovery for sim sensors |

---

## Current Status (2026-03-31)

### What Works
- Drone flies to 2.5m and hovers with **optical flow position hold** (holds position, returns when disturbed)
- All 5 sensor topics publish: optical flow, flow camera, rangefinder, 2D lidar, mono camera
- HD camera video recorded during flight (1280x720, multi-threaded, MP4 via ffmpeg)
- Lidar scan captured during hover (1080 points, PDF)
- Optical flow quality captured (PDF)
- MAVSDK flight demo with sensor verification
- Launch script with GUI and headless modes
- Multiple flights per session without PX4 restart

### Known Limitations
- **Landing drift**: below ~1m altitude, optical flow loses ground texture and position hold degrades — drone may drift on final approach
- **`commander set_heading 0` is manual**: must be typed in pxh> before flight (MAVSDK shell command doesn't work reliably)
- **Post-landing tip-over**: simulation lacks landing gear physics, drone may tip after touchdown
- **GStreamer broken on macOS**: camera video uses PNG+ffmpeg instead

### Key Discoveries
- **Altitude matters**: optical flow needs 2.5m+ for good feature tracking (at 1m the flow camera sees too little ground texture)
- **Never `param set` EKF2 at runtime**: setting EKF2_HGT_REF via MAVSDK before flight resets the EKF2 estimator and destroys optical flow fusion
- **Stock PX4 defaults work**: only GPS disable is needed, all other EKF2 params at defaults

---

## Sensor Architectures

### Optical Flow
```
flow_camera (100x100, 50Hz) → OpticalFlowSystem plugin → gz optical_flow topic
  → gz_bridge → sensor_optical_flow uORB → VehicleOpticalFlow → EKF2
```

### Rangefinder
```
gpu_lidar (1 ray, 50Hz) → gz_bridge → distance_sensor uORB → EKF2 (height correction)
```

### 2D Lidar
```
lidar_2d_v2 (1080 samples, 270°, 30Hz) → Gazebo topic (not used by PX4, for companion computer)
```

### Mono Camera
```
camera (1280x720, 30Hz) → Gazebo topic → captured by demo_flight.py → MP4 video
```

---

## Key Rules

1. **NO GPS** — do not enable `SIM_GPS_USED`, `EKF2_GPS_CTRL`
2. **Keep barometer enabled** — baro provides stable height reference, rangefinder provides correction
3. **Use MAVSDK-Python** for flight control — same code on real drone
4. **Use stock PX4 defaults** — only change what's necessary (GPS disable + arming overrides)
5. **NEVER `param set` EKF2 params at runtime** — use `param set-default` in airframe only
6. **PX4 manages Gazebo** — non-standalone mode, no separate `gz sim -s`
7. **`env.sh` auto-detects** SDK, homebrew prefix, network IP — no hardcoded paths
8. **Fly at 2.5m+** — optical flow needs altitude for ground texture visibility

---

## Diagnostic Commands (in `pxh>`)

```bash
ekf2 status                    # must show update events > 0
listener estimator_status_flags # sensor fusion flags
listener vehicle_optical_flow   # optical flow data
listener distance_sensor        # rangefinder
listener sensor_accel           # IMU (z should be ~-9.8)
commander check                 # preflight check status
```
