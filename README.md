# Scarecrow Drone

Autonomous GPS-denied indoor drone simulation — Holybro X500 V2 with full sensor stack, powered by PX4 SITL and Gazebo Harmonic.

University final project: proves indoor flight using only optical flow + rangefinder for state estimation, with no GPS dependency. The same flight code runs on the real drone.

## Sensor Stack

| Sensor | Hardware | Gazebo Model | Role |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity |
| Downward rangefinder | TF-Luna | `LW20` / `gpu_lidar` | Height correction |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance |
| Mono camera | Pi Camera 3 | `mono_cam` (1280x720) | Visual awareness |

GPS is disabled. Height uses barometer (Pixhawk built-in) + rangefinder correction.

## Repository Structure

```
scarecrow-drone/
├── scarecrow/                       — Python package (pip install -e .)
│   ├── sensors/lidar/               — LidarSource ABC, GazeboLidar, RPLidarSource
│   ├── controllers/                 — WallFollowController, rotate_90()
│   └── navigation/                  — Future: SLAM, path planning
├── scripts/
│   ├── shell/
│   │   ├── launch.sh                — One-command launcher (GUI or headless)
│   │   └── env.sh                   — Shared environment variables
│   └── flight/
│       ├── demo_flight.py           — Hover demo + HD video + sensor capture
│       ├── wall_follow.py           — Single wall follow using lidar
│       ├── room_circuit.py          — Full room perimeter (4 legs + 4 turns)
│       └── sensor_check.py          — Ground-only sensor data capture
├── airframes/4022_gz_holybro_x500   — PX4 airframe (GPS disabled, stock defaults)
├── config/server.config             — Gazebo server plugins (Sensors, OpticalFlow)
├── models/
│   ├── holybro_x500/model.sdf       — Composite drone model (x500 + all 4 sensors)
│   └── mono_cam/model.sdf           — Camera model (1280x720 HD)
├── worlds/
│   ├── default.sdf                  — Open world with checkerboard floor
│   └── indoor_room.sdf             — 20m clean room with colored walls, full checkerboard
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
./scripts/shell/launch.sh default --headless # headless mode
```

### 2. Configure PX4

Once you see `pxh>` prompt:
```
commander set_heading 0
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
# In pxh>: commander set_heading 0
python3 scripts/flight/wall_follow.py
```

Follows the left wall at 2m distance, stops 2m from the front wall.

### Room Circuit

```bash
PX4_GZ_MODEL_POSE="-7,-7,0,0,0,0" ./scripts/shell/launch.sh
# In pxh>: commander set_heading 0
python3 scripts/flight/room_circuit.py
```

Flies the full room perimeter (4 legs + 4 turns) and lands at the starting position. Configurable wall side and distances. Saves lidar scan PDFs at each turn for diagnostics.

### Scarecrow Package

The navigation logic lives in a reusable Python package:

```bash
pip install -e .  # install in dev mode
```

```python
from scarecrow.sensors.lidar.gazebo import GazeboLidar     # simulation
from scarecrow.sensors.lidar.rplidar import RPLidarSource   # real hardware
from scarecrow.controllers.wall_follow import WallFollowController
from scarecrow.controllers.rotation import rotate_90
```

Same code runs on Gazebo and on the real drone — only the lidar source changes.

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
