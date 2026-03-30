# Scarecrow Drone

Autonomous GPS-denied indoor drone simulation — Holybro X500 V2 with full sensor stack, powered by PX4 SITL and Gazebo Harmonic.

University final project: proves indoor flight using only optical flow + rangefinder for state estimation, with no GPS dependency. The same flight code runs on the real drone.

## Sensor Stack

| Sensor | Hardware | Gazebo Model | Role |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity |
| Downward rangefinder | TF-Luna | `LW20` / `gpu_lidar` | Height correction |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance |
| Mono camera | Pi Camera 3 | `mono_cam` (320x240) | Visual awareness |

GPS is disabled. Height uses barometer (Pixhawk built-in) + rangefinder correction.

## Repository Structure

```
scarecrow-drone/
├── airframes/4022_gz_holybro_x500   — PX4 airframe (GPS disabled, stock defaults)
├── config/server.config             — Gazebo server plugins (Sensors, OpticalFlow)
├── models/
│   ├── holybro_x500/model.sdf       — Composite drone model (x500 + all 4 sensors)
│   └── mono_cam/model.sdf           — Camera model (320x240 for recording)
├── worlds/
│   ├── default.sdf                  — Open world with checkerboard floor
│   └── indoor_room.sdf             — 20m room with colored walls and obstacles
├── scripts/
│   ├── launch.sh                    — One-command launcher (GUI or headless)
│   ├── hover_test.py                — MAVSDK flight test + sensor capture + video
│   ├── sensor_demo.py               — Standalone sensor data capture
│   └── env.sh                       — Shared environment variables
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

This installs: cmake, ninja, gcc, Gazebo Harmonic (gz-harmonic), OpenCV, GStreamer, protobuf, and all Python build dependencies.

### 3. Install Flight Test Dependencies

```bash
python3 -m venv .venv-mavsdk
source .venv-mavsdk/bin/activate
pip install mavsdk matplotlib numpy opencv-python-headless pillow
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

### 3. Install PX4 Python Dependencies

```bash
pip3 install --break-system-packages -r px4/Tools/setup/requirements.txt
```

### 4. Install Flight Test Dependencies

```bash
python3 -m venv .venv-mavsdk
source .venv-mavsdk/bin/activate
pip install mavsdk matplotlib numpy opencv-python-headless pillow
```

### 5. Install ffmpeg

```bash
brew install ffmpeg
```

### 3. Launch Simulation

```bash
./scripts/launch.sh                    # GUI + indoor room (default)
./scripts/launch.sh default            # GUI + open world
./scripts/launch.sh default --headless # headless mode
```

### 4. Configure PX4

Once you see `pxh>` prompt:
```
commander set_ekf_origin 0 0 0
commander set_heading 0
param set EKF2_HGT_REF 0
```

### 5. Run Flight Test

In a second terminal:
```bash
source .venv-mavsdk/bin/activate
python3 scripts/hover_test.py
```

## Flight Test Output

The test verifies sensors, flies to 1.0m, hovers, captures sensor data, and lands:

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
- `flight_camera.mp4` — camera video during flight
- `lidar_scan.pdf` — 2D lidar top-down scan of room
- `optical_flow.pdf` — optical flow quality chart
- `camera_ground.png` / `camera_flight.png` — camera snapshots

## Real Drone

The hover test uses MAVSDK — same code runs on real hardware. Only the connection changes:

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
