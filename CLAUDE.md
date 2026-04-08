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
├── scarecrow/                     ← Python package (pip install -e .)
│   ├── sensors/lidar/
│   │   ├── base.py                ← LidarSource ABC + LidarScan (SVD wall alignment)
│   │   ├── gazebo.py              ← GazeboLidar (simulation)
│   │   └── rplidar.py             ← RPLidarSource (real hardware)
│   ├── controllers/
│   │   ├── wall_follow.py         ← WallFollowController (left/right, PD + SVD yaw)
│   │   ├── rotation.py            ← rotate_90() (compass + lidar SVD alignment)
│   │   ├── distance_stabilizer.py ← DistanceStabilizerController (optional front/rear/left/right targets)
│   │   └── front_wall_detector.py ← FrontWallDetector (obstacle-aware front stop, cluster validation)
│   └── navigation/                ← future: SLAM, path planning
├── scripts/
│   ├── shell/
│   │   ├── launch.sh              ← one-command launcher (GUI or headless)
│   │   └── env.sh                 ← shared environment variables
│   └── flight/
│       ├── demo_flight.py         ← MAVSDK flight demo + HD video + sensor capture
│       ├── wall_follow.py         ← single wall follow using lidar
│       ├── room_circuit.py        ← full room perimeter (4 legs + 4 turns)
│       └── sensor_check.py        ← ground-only sensor data capture (no flight)
├── airframes/
│   ├── 4022_gz_holybro_x500       ← custom airframe (GPS disabled, stock defaults)
│   └── 4022_gz_holybro_x500.post  ← post-start hook: auto-runs commander set_heading 0
├── config/
│   └── server.config              ← Gazebo server plugins (Sensors + OpticalFlowSystem)
├── models/
│   ├── holybro_x500/model.sdf     ← composite model: x500 + all 4 sensors
│   ├── mono_cam/model.sdf         ← camera at 640x360 @ 15fps (reduced for WSL perf)
│   ├── military_drone/model.sdf   ← static obstacle model for garage world
│   ├── pigeon_billboard/          ← flat panel with pigeon texture for YOLO detection
│   └── yolo/best_v4.pt            ← trained YOLOv8 pigeon detector (22MB, bundled)
├── worlds/
│   ├── default.sdf                ← open world with checkerboard floor
│   ├── indoor_room.sdf            ← 20m clean room + 1 pigeon billboard @ 3m from spawn
│   └── drone_garage.sdf           ← garage environment with military drone obstacle
├── webapp/                        ← Web UI for sim + detection
│   ├── backend/                   ← FastAPI server (port 5000)
│   │   ├── app.py                 ← API endpoints
│   │   ├── database/db.py         ← SQLite: flights + detection_images
│   │   └── services/
│   │       ├── sim_service.py     ← Launches/monitors PX4+Gazebo, tracks launch stages
│   │       └── detection_service.py ← Manages detect_pigeons.py subprocess
│   ├── frontend/                  ← React 19 + TypeScript UI
│   │   └── src/
│   │       ├── pages/Dashboard.tsx   ← Tabs: Control / History, polling
│   │       ├── components/
│   │       │   ├── SimControl.tsx    ← Connect/Start/Stop + launch checklist + live timer
│   │       │   ├── FlightHistory.tsx ← Past detection sessions list
│   │       │   └── FlightModal.tsx   ← Summary / Detections / Recording tabs
│   │       └── services/api.ts       ← Backend API client
│   └── Start Scarecrow.bat        ← One-click launcher (syncs to WSL + starts both)
├── scripts/flight/detect_pigeons.py ← Gazebo camera → YOLOv8 pigeon detection
├── pyproject.toml                 ← package config (pip install -e .)
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

**Runtime commands** — both are now automated, no manual entry needed:
- `commander set_ekf_origin 0 0 0` — set by the flight script via MAVSDK
- `commander set_heading 0` — set by `4022_gz_holybro_x500.post` hook at PX4 startup

**Critical rules**:
- Don't over-configure EKF2. Stock defaults work. Only disable GPS.
- **NEVER `param set` EKF2 params at runtime** — it resets the estimator and destroys optical flow fusion.

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

No manual commands needed. `set_heading 0` runs automatically via the `.post` hook, and `set_ekf_origin` is handled by the flight script.

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
20m x 20m clean room with:
- **Red** wall (north), **Blue** wall (south), **Green** wall (east), **Yellow** wall (west)
- **Full 20m x 20m checkerboard floor** (400 tiles, 1m each, wall-to-wall) for optical flow
- No obstacles (clean for wall-follow navigation testing)

### drone_garage.sdf
Garage environment with a static military drone model placed as an obstacle. Used to test `FrontWallDetector` obstacle discrimination — the parked drone is in the space but not on the flight path, so the detector should not trigger a wall stop.

---

## Pigeon Detection (YOLOv8)

The sim includes a full pigeon detection pipeline using the `best_v4.pt` model trained in the sibling `scarecrow_drone` project.

### Detection Pipeline
```
Gazebo mono_cam (640x360) → gz topic -e → detect_pigeons.py → YOLOv8 best_v4.pt → annotated PNGs
```

- **Model**: `models/yolo/best_v4.pt` — custom-trained YOLOv8 (single class: `pigeon`)
- **Target**: `pigeon_billboard` model in `indoor_room.sdf` — flat panel with real pigeon texture, standing 3m from spawn. Detected at ~89% confidence.
- **Script**: `scripts/flight/detect_pigeons.py` — captures camera frames via `gz topic -e`, runs YOLO inference, saves annotated detections.
- **Frame rate**: ~0.2 FPS on WSL (capture is the bottleneck, not inference)
- **Output**: `DETECTION_IMAGE:<path>` stdout lines (parsed by webapp backend), saved to `webapp/output/<flight_id>/detections/`

---

## Webapp (One-Click Launcher)

Full web UI for running the sim and detection without touching the terminal.

### Stack
- **Backend**: FastAPI on port 5000 (runs inside WSL)
- **Frontend**: React 19 + TypeScript on port 3000 (runs on Windows)
- **Database**: SQLite at `webapp/backend/database/scarecrow.db` (flights + detection_images)
- **Launcher**: `webapp/Start Scarecrow.bat` — syncs files to WSL, starts both servers, opens browser

### Workflow
1. Double-click `Start Scarecrow.bat`
2. Click **Connect** → backend runs `launch.sh` in WSL, checklist UI shows real-time stages (cleanup → build → gazebo → sensors → ready)
3. Click **Start Detection** → backend spawns `detect_pigeons.py`, creates flight in DB, parses `DETECTION_IMAGE:` lines
4. Click **Stop Detection** → finalizes flight record with pigeon count
5. **Detection History** tab → click a flight to see summary / detection images / recording

### Key Files
- `webapp/backend/services/sim_service.py` — parses `launch.sh` stdout to track stages, sends `commander set_ekf_origin 0 0 0` + `set_heading 0` via process stdin
- `webapp/backend/services/detection_service.py` — spawns `detect_pigeons.py`, parses pigeon counts and `DETECTION_IMAGE:` lines for DB
- `webapp/backend/app.py` — REST API: `/api/sim/connect`, `/api/flight/start|stop`, `/api/flights`, etc.
- `webapp/frontend/src/pages/Dashboard.tsx` — polls sim status (3s) and flight status (2s), manages modal state
- `webapp/frontend/src/components/SimControl.tsx` — launch checklist, live timer, start/stop buttons

### Performance Notes (WSL)
- PX4 `make px4_sitl` reconfigures cmake every launch (~1-2 min). First launch after code changes is slow.
- Gazebo camera capture via `gz topic -e -n 1` takes ~5s per frame — limits detection to ~0.2 FPS.
- `mono_cam` reduced to 640x360 @ 15fps, clip far distance 100m, shadows disabled for WSL GPU performance.
- `export __GLX_VENDOR_LIBRARY_NAME=nvidia` + `LIBGL_ALWAYS_SOFTWARE=1` help on NVIDIA laptops with WSLg.

---

## Files Changed from Upstream PX4

| File | Change |
|---|---|
| `ROMFS/.../4022_gz_holybro_x500` | Custom airframe: GPS disabled, arming overrides |
| `ROMFS/.../px4-rc.gzsim` | Added `sensors stop/start` after gz_bridge (EKF2 init race fix) |
| `src/.../GZMixingInterfaceESC.cpp` | float→double cast fix for Apple clang |
| `src/.../voted_sensors_update.cpp` | IMU priority auto-recovery for sim sensors |

---

## Current Status (2026-04-08)

### What Works
- Drone flies to 2.5m and hovers with **optical flow position hold**
- **Wall following**: follows left or right wall at configurable distance using lidar PD + SVD yaw correction
- **90° rotation**: compass coarse turn + lidar SVD fine alignment (works in GPS-denied mode)
- **Room circuit**: full perimeter flight (4 legs + 4 turns)
- **Post-turn stabilization**: reusable distance controller holds configured side/rear targets before each leg
- **Obstacle-aware front stop**: `FrontWallDetector` validates front reading is a real wall before triggering stop
- **YOLOv8 pigeon detection**: `best_v4.pt` detects pigeon billboards live from Gazebo camera at ~89% confidence
- **Webapp**: one-click `Start Scarecrow.bat` launches FastAPI backend + React UI. Connect button shows launch checklist; Start Detection runs YOLO on camera feed; History tab shows past sessions with detection images and video recording
- All 5 sensor topics publish: optical flow, flow camera, rangefinder, 2D lidar, mono camera
- `scarecrow` Python package: reusable sensor interfaces + controllers (pip installable)
- Same package runs on Gazebo (sim) and real drone (RPLidar A1M8 via USB)
- Multiple flights per session without PX4 restart

### Known Limitations
- **Landing drift**: below ~1m altitude, optical flow loses ground texture — drone may drift on final approach
- **`commander set_heading 0` is automated**: runs via `4022_gz_holybro_x500.post` hook at startup
- **PX4 compass drift**: GPS-denied heading drifts ~10-15° from physical heading, compensated by lidar SVD alignment
- **GStreamer broken on macOS**: camera video uses PNG+ffmpeg instead
- **FrontWallDetector thresholds untested with real obstacles**: tuned in simulation against clean walls — needs flight data validation
- **WSL detection FPS is slow**: ~0.2 FPS because `gz topic -e -n 1` takes ~5s per frame capture. Inference itself is fast. First pigeon detection after clicking Start usually shows up after 20-25s.
- **Flat billboard vs 3D mesh**: `pigeon_billboard` is a flat panel with a real pigeon photo texture. YOLO detects it because the texture itself is a real photo. A 3D pigeon mesh would render differently and might not trigger the detector trained on photos.
- **MAVSDK server crashes on WSL2**: `mavsdk_server` binary segfaults under WSL2. The webapp does not use MAVSDK — it manages detection as a subprocess and sends PX4 commands via process stdin. Flight code that needs MAVSDK (`demo_flight.py` etc.) still works on macOS/native Linux.

### Key Discoveries
- **Altitude matters**: optical flow needs 2.5m+ for good feature tracking
- **Never `param set` EKF2 at runtime**: resets the estimator, destroys optical flow fusion
- **Stock PX4 defaults work**: only GPS disable is needed
- **Unified lidar contract**: simulation and real adapter both use strict 360° scans (`-pi..+pi`, 1440 samples)
- **Compass + lidar SVD**: compass for coarse turns, lidar SVD for precise wall alignment — compensates for GPS-denied heading drift
- **Front stop needs perception, not just distance**: raw `front_distance()` triggers false stops from off-axis obstacles; cluster validation + temporal confirmation is required

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
lidar_2d_v2 (1440 samples, 360°, 30Hz) → Gazebo topic (not used by PX4, for companion computer)
```

### Mono Camera
```
camera (1280x720, 30Hz) → Gazebo topic → captured by demo_flight.py → MP4 video
```

---

## WSL Setup (Tomer's machine)

- **WSL distro**: `Ubuntu-22.04` (NOT the default `Ubuntu`)
- Always open with: `wsl -d Ubuntu-22.04` from PowerShell
- Repo location inside WSL: `~/scarecrow-drone`
- `.wslconfig` at `C:\Users\tomer\.wslconfig` — needs `memory=8GB` minimum (PX4 build fails with less)
- Build with `make px4_sitl_default -j2` if memory is tight

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
