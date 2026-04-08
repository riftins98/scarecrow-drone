# Scarecrow Drone

Autonomous GPS-denied indoor drone simulation — Holybro X500 V2 with full sensor stack, powered by PX4 SITL and Gazebo Harmonic.

University final project: proves indoor flight using only optical flow + rangefinder for state estimation, with no GPS dependency. The same flight code runs on the real drone.

## Sensor Stack

| Sensor | Hardware | Gazebo Model | Role |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity |
| Downward rangefinder | TF-Luna | `LW20` / `gpu_lidar` | Height correction |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance |
| Mono camera | Pi Camera 3 | `mono_cam` (640x360) | YOLOv8 pigeon detection |

GPS is disabled. Height uses barometer (Pixhawk built-in) + rangefinder correction. The camera feeds a live YOLOv8 pigeon detector (`models/yolo/best_v4.pt`).

## Lidar Contract

Lidar is unified across simulation and real hardware (RPLidar adapter):
- Full-circle scan: `-pi .. +pi` (360°)
- Sample count: `1440`
- Direction mapping: `0°=front`, `+90°=left`, `-90°/270°=right`, `±180°=rear`

## Repository Structure

```
scarecrow-drone/
├── scarecrow/                       — Python package (pip install -e .)
│   ├── sensors/lidar/               — LidarSource ABC, GazeboLidar, RPLidarSource
│   ├── controllers/                 — WallFollowController, rotate_90(), DistanceStabilizerController, FrontWallDetector
│   └── navigation/                  — Future: SLAM, path planning
├── scripts/
│   ├── shell/
│   │   ├── launch.sh                — One-command launcher (GUI or headless)
│   │   └── env.sh                   — Shared environment variables
│   └── flight/
│       ├── demo_flight.py           — Hover demo + HD video + sensor capture
│       ├── detect_pigeons.py        — Live YOLOv8 pigeon detection from Gazebo camera
│       ├── wall_follow.py           — Single wall follow using lidar
│       ├── room_circuit.py          — Full room perimeter (4 legs + 4 turns)
│       └── sensor_check.py          — Ground-only sensor data capture
├── airframes/4022_gz_holybro_x500   — PX4 airframe (GPS disabled, stock defaults)
├── config/server.config             — Gazebo server plugins (Sensors, OpticalFlow)
├── models/
│   ├── holybro_x500/model.sdf       — Composite drone model (x500 + all 4 sensors)
│   ├── mono_cam/model.sdf           — Camera model (640x360 @ 15fps)
│   ├── military_drone/model.sdf     — Static obstacle model for garage world
│   ├── pigeon_billboard/            — Flat panel with pigeon texture (detection target)
│   └── yolo/best_v4.pt              — Trained YOLOv8 pigeon detector (22MB, bundled)
├── worlds/
│   ├── default.sdf                  — Open world with checkerboard floor
│   ├── indoor_room.sdf              — 20m clean room + pigeon billboard
│   └── drone_garage.sdf             — Garage environment with military drone obstacle
├── webapp/                          — Web UI (one-click launcher)
│   ├── backend/                     — FastAPI (port 5000)
│   ├── frontend/                    — React 19 + TypeScript (port 3000)
│   └── Start Scarecrow.bat          — Windows one-click launcher
├── pyproject.toml                   — Package config
├── px4/                             — PX4-Autopilot submodule (branch: scarecrow)
└── .venv-mavsdk/                    — Python venv (create with: python3 -m venv .venv-mavsdk)
```

## Supported Platforms

| Platform | Status | Notes |
|---|---|---|
| Ubuntu 22.04 / 24.04 | Fully supported | Easiest setup, PX4's primary platform |
| macOS (Apple Silicon) | Tested, works | Needs SDK workaround (auto-detected) |
| macOS (Intel) | Should work | Untested |
| Windows | Not supported | Use WSL2 with Ubuntu |

## Setup — Ubuntu 22.04 / 24.04

### 1. Clone

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone
```

### 2. Install PX4 Dependencies + Gazebo Harmonic

PX4's setup script installs everything: build tools, Gazebo Harmonic, Python packages, GStreamer.

```bash
cd px4
bash Tools/setup/ubuntu.sh
cd ..
```

### 3. Install Flight Test Dependencies

```bash
python3 -m venv .venv-mavsdk
source .venv-mavsdk/bin/activate
pip install -r requirements.txt
```

### 4. Install ffmpeg (for video output)

```bash
sudo apt install ffmpeg
```

## Setup — macOS (Apple Silicon)

### 1. Clone

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone
```

### 2. Install Gazebo + Dependencies via Homebrew

```bash
brew install gz-sim8 opencv qt@5
```

### 3. Install Flight Test Dependencies

```bash
python3 -m venv .venv-mavsdk
source .venv-mavsdk/bin/activate
pip install -r requirements.txt
```

### 4. Install ffmpeg

```bash
brew install ffmpeg
```

## Running the Simulation

### 1. Launch

```bash
./scripts/shell/launch.sh                    # GUI + indoor room (default)
./scripts/shell/launch.sh default            # GUI + open world
./scripts/shell/launch.sh drone_garage       # GUI + garage with obstacle
./scripts/shell/launch.sh default --headless # headless mode
```

### 2. Configure PX4

`commander set_heading 0` is now applied automatically during launch.

If you want to disable that behavior for a run:
```bash
SCARECROW_AUTO_SET_HEADING=0 ./scripts/shell/launch.sh
```

(`set_ekf_origin` is handled automatically by the flight script)

### 3. Run Flight Demo

In a second terminal:
```bash
source .venv-mavsdk/bin/activate
python3 scripts/flight/demo_flight.py
```

The drone takes off to 2.5m, hovers with optical flow position hold, captures sensor data and HD video, then lands. You can run this multiple times without restarting PX4.

## Flight Demo Output

```
  SENSOR VERIFICATION — GPS-Denied Navigation
  [OK] EKF2_GPS_CTRL = 0 -- GPS disabled
  [OK] EKF2_OF_CTRL = 1 -- Optical flow enabled
  [OK] SYS_HAS_GPS = 0 -- GPS hardware disabled

  Gazebo Sensor Topics
  [OK] Optical flow (MTF-01)
  [OK] Flow camera
  [OK] Downward rangefinder
  [OK] 2D lidar (RPLidar)
  [OK] Mono camera (Pi Cam)
```

Output files saved to `output/`:
- `flight_camera.mp4` — HD camera video during flight (real-time speed)
- `lidar_scan.pdf` — 2D lidar top-down scan of room
- `optical_flow.pdf` — optical flow quality chart
- `camera_ground.png` / `camera_flight.png` — camera snapshots

## Wall Follow & Room Circuit

### Wall Follow

```bash
PX4_GZ_MODEL_POSE="-7,7,0,0,0,0" ./scripts/shell/launch.sh
python3 scripts/flight/wall_follow.py
```

Follows the left wall at 2m distance, stops 2m from the front wall.

### Room Circuit

```bash
PX4_GZ_MODEL_POSE="-7,-7,0,0,0,0" ./scripts/shell/launch.sh
python3 scripts/flight/room_circuit.py
```

Flies the full room perimeter (4 legs + 4 turns). Configurable wall side and distances. Saves lidar scan PDFs at each turn for diagnostics.

After each turn, the drone runs post-turn stabilization using distance constraints before starting the next leg:
- Side wall target (`left` or `right` based on `WALL_SIDE`)
- Rear wall target

Current defaults in `scripts/flight/room_circuit.py`:
- `POST_TURN_SIDE_TARGET = 2.0`
- `POST_TURN_REAR_TARGET = 2.0`

Front-wall stopping uses `FrontWallDetector` to validate that the lidar reading is a real wall (wide cluster, centered, multi-frame confirmed) before stopping — avoids false stops from off-axis obstacles not on the flight path.

### Scarecrow Package

The navigation logic lives in a reusable Python package:

```bash
pip install -e .  # install in dev mode
```

```python
from scarecrow.sensors.lidar.gazebo import GazeboLidar     # simulation
from scarecrow.sensors.lidar.rplidar import RPLidarSource   # real hardware
from scarecrow.controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from scarecrow.controllers.wall_follow import WallFollowController
from scarecrow.controllers.front_wall_detector import FrontWallDetector
from scarecrow.controllers.rotation import rotate_90
```

Same code runs on Gazebo and on the real drone — only the lidar source changes.

## Pigeon Detection (YOLOv8)

The sim includes a live pigeon detection pipeline using a custom-trained YOLOv8 model (`models/yolo/best_v4.pt`). The `indoor_room.sdf` world spawns a `pigeon_billboard` (flat panel with a real pigeon photo) 3m from the drone spawn, which YOLO detects at ~89% confidence.

### Run detection manually

With the sim running:

```bash
source .venv-mavsdk/bin/activate
python3 scripts/flight/detect_pigeons.py --confidence 0.3 --duration 30
```

Annotated frames are saved to `output/detections/`.

## Webapp — One-Click Launcher

Full web UI for running the sim + detection without touching a terminal.

### Start it (Windows)

Double-click:

```
webapp/Start Scarecrow.bat
```

It will:
1. Sync backend files + detection script + YOLO model to WSL
2. Start the FastAPI backend in WSL on port 5000
3. Start the React frontend on port 3000
4. Open `http://localhost:3000` in your browser

### UI Workflow

- **Drone Control** tab:
  - Click **Connect** → launches PX4 + Gazebo, shows a real-time checklist (cleanup → build → gazebo → sensors → ready)
  - Click **Start Detection** → runs `detect_pigeons.py`, live counters for frames/pigeons, timer
  - Click **Stop Detection** → finalizes the flight record
- **Detection History** tab:
  - Lists all past sessions with date, duration, pigeon count
  - Click a session to open a modal with Summary / Detections (image gallery) / Recording tabs

### Stack

- **Backend**: FastAPI (`webapp/backend/app.py`) with SQLite (`webapp/backend/database/scarecrow.db`)
- **Frontend**: React 19 + TypeScript (`webapp/frontend/src/`)
- **Detection integration**: backend spawns `detect_pigeons.py` as a subprocess, parses `DETECTION_IMAGE:` lines for the database

## Real Drone

The flight demo uses MAVSDK — same code runs on real hardware. Only the connection changes:

```python
# Simulation
SYSTEM_ADDRESS = "udp://:14540"

# Real drone (companion computer -> Pixhawk via USB)
SYSTEM_ADDRESS = "serial:///dev/ttyACM0:921600"
```

## Kill Everything

```bash
pkill -f "gz sim"; pkill -x px4
rm -f /tmp/px4_lock-0 /tmp/px4-sock-0
```
