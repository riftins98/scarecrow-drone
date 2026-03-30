# Scarecrow Drone — Full Project Context

## Project Goal

University final project: simulate a Holybro X500 V2 drone with full sensor stack for GPS-denied indoor flight. The simulation replaces delayed hardware and must prove **all sensors work** to get project approval. If the simulation works, the same flight code runs on the real drone.

### Sensor Stack (must match real hardware)

| Sensor | Hardware | Gazebo Model | Purpose |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity estimation |
| Downward rangefinder | TF-Luna | `LW20` + `lidar_sensor_link` (gpu_lidar) | Height correction |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance / self-position |
| Mono camera | Pi Camera 3 | `mono_cam` (320x240) | Visual awareness |

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
│   └── mono_cam/model.sdf         ← camera at 320x240 for video recording
├── worlds/
│   ├── default.sdf                ← open world with checkerboard floor
│   └── indoor_room.sdf            ← 20m room: colored walls, obstacles, checkerboard floor
├── scripts/
│   ├── launch.sh                  ← one-command launcher (GUI or headless)
│   ├── hover_test.py              ← MAVSDK flight test + video + sensor capture
│   ├── sensor_demo.py             ← standalone sensor data capture
│   └── env.sh                     ← shared environment variables
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
EKF2_HGT_REF 0       # height reference = barometer (GPS unavailable)

# Allow arming without GPS
COM_ARM_WO_GPS 1, COM_RC_IN_MODE 1
NAV_DLL_ACT 0, NAV_RCL_ACT 0
```

Everything else is PX4 stock defaults. Barometer, magnetometer, IMU — all at defaults.

**Runtime params** (set in `pxh>` before each flight):
```
commander set_ekf_origin 0 0 0
commander set_heading 0
param set EKF2_HGT_REF 0
```

**Key lesson**: Don't over-configure EKF2. The stock x500_flow with only GPS disabled flies perfectly. Disabling baro caused altitude control failures.

---

## Launch

### One Command

```bash
./scripts/launch.sh                    # GUI + indoor room (default)
./scripts/launch.sh default            # GUI + open world
./scripts/launch.sh default --headless # headless mode
```

The launch script:
1. Kills previous PX4/Gazebo sessions
2. Copies airframe, config, models, worlds to PX4 dirs
3. Builds PX4 (incremental, fast after first build)
4. Launches PX4 + Gazebo (PX4 manages Gazebo)

### After Launch

In `pxh>`:
```
commander set_ekf_origin 0 0 0
commander set_heading 0
param set EKF2_HGT_REF 0
```

### Flight Test

In a second terminal:
```bash
source .venv-mavsdk/bin/activate
python3 scripts/hover_test.py
```

The script:
1. Verifies GPS is disabled and sensors are publishing
2. Sets `EKF2_HGT_REF 0` via MAVSDK
3. Arms and takes off using PX4's built-in takeoff controller
4. Records camera video (raw frames to disk, builds MP4 after landing)
5. Captures lidar scan + optical flow during hover
6. Lands and produces output files

### Output Files

Saved to `output/` (gitignored):
- `flight_camera.mp4` — camera video from flight
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
- Checkerboard floor

The drone drifts horizontally ~4s into hover (no optical flow position hold) and may hit walls. Use for sensor demos (lidar scan shows room), not for long flights.

---

## Files Changed from Upstream PX4

| File | Change |
|---|---|
| `ROMFS/.../4022_gz_holybro_x500` | Custom airframe: GPS disabled, baro height ref |
| `ROMFS/.../px4-rc.gzsim` | Added `sensors stop/start` after gz_bridge (EKF2 init race fix) |
| `src/.../GZMixingInterfaceESC.cpp` | float→double cast fix for Apple clang |
| `src/.../voted_sensors_update.cpp` | IMU priority auto-recovery for sim sensors |

---

## Current Status (2026-03-30)

### What Works
- Drone flies to ~1.0m and hovers stably (5+ seconds in open world)
- All 5 sensor topics publish: optical flow, flow camera, rangefinder, 2D lidar, mono camera
- Camera video recorded during flight (320x240, ~130 frames, MP4 via ffmpeg)
- Lidar scan captured during hover (1080 points, PDF)
- Optical flow quality captured (PDF)
- MAVSDK hover test with sensor verification
- Launch script with GUI and headless modes

### Known Limitations
- **Indoor room hover**: drone drifts horizontally after ~4s and may crash into walls (optical flow not fusing for position hold)
- **Optical flow not fusing**: `cs_opt_flow` stays False — EKF2 chicken-and-egg with terrain estimation
- **Post-landing tip-over**: simulation lacks landing gear physics, drone tips after touchdown (PX4 enters failsafe)
- **PX4 restart needed between flights**: post-crash attitude failure persists until restart
- **GStreamer broken on macOS**: camera video uses PNG+ffmpeg instead

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
camera (320x240, 30Hz) → Gazebo topic → captured by hover_test.py → MP4 video
```

---

## Key Rules

1. **NO GPS** — do not enable `SIM_GPS_USED`, `EKF2_GPS_CTRL`
2. **Keep barometer enabled** — baro provides stable height reference, rangefinder provides correction
3. **Use MAVSDK-Python** for flight control — same code on real drone
4. **Use stock PX4 defaults** — only change what's necessary (GPS disable + height ref)
5. **PX4 manages Gazebo** — non-standalone mode, no separate `gz sim -s`
6. **`env.sh` auto-detects** SDK, homebrew prefix, network IP — no hardcoded paths

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
