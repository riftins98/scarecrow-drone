# Scarecrow Drone

Autonomous GPS-denied indoor drone simulation — Holybro X500 V2 with full sensor stack, powered by PX4 SITL and Gazebo Harmonic.

University final project: proves indoor flight using only optical flow + rangefinder for state estimation, with no GPS dependency. The same flight code runs on the real drone.

---

## What It Does

The drone takes off to 2.5m, holds position using optical flow (no GPS), and runs a live YOLOv8 pigeon detector against the camera feed during hover. A web UI provides one-click control: launch the simulation, start a detection flight, and browse past sessions with detection images and recorded video.

---

## Sensor Stack

| Sensor | Hardware | Simulation Model | Role |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity estimation |
| Downward rangefinder | TF-Luna | `LW20` / `gpu_lidar` | Height correction |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance |
| Mono camera | Pi Camera 3 | `mono_cam` (640x360) | YOLOv8 pigeon detection |

GPS is disabled. Height uses barometer (Pixhawk built-in) + rangefinder correction.

---

## Setup

**Requires Python 3.11** — do not use 3.12 or later (torch/ultralytics compatibility).

### Ubuntu 22.04 / 24.04

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone

# Install PX4 build tools + Gazebo Harmonic
cd px4 && bash Tools/setup/ubuntu.sh && cd ..

# Install Python dependencies
python3.11 -m venv .venv-mavsdk
source .venv-mavsdk/bin/activate
pip install -r requirements.txt
pip install -e .

# Install ffmpeg (for video output)
sudo apt install ffmpeg
```

### macOS (Apple Silicon / Intel)

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone

# Install Gazebo + dependencies
brew install gz-sim8 opencv qt@5 ffmpeg

# Install Python dependencies
python3.11 -m venv .venv-mavsdk
source .venv-mavsdk/bin/activate
pip install -r requirements.txt
pip install -e .
```

---

## Running the Web UI

The primary interface is a one-click launcher that opens a browser-based control panel.

**macOS:**
```bash
bash "webapp/Start Scarecrow Mac.sh"
```

**Windows (WSL2):**
```
Double-click: webapp/Start Scarecrow.bat
```

Both launchers start the FastAPI backend (port 8000) and the React frontend (port 3000), then open `http://localhost:3000` in the browser.

### UI Workflow

1. **Connect** — launches PX4 + Gazebo with a live checklist (cleanup → build → Gazebo → sensors → ready)
2. **Start Detection** — drone takes off to 2.5m, hovers, runs YOLOv8 pigeon detection, records full flight video
3. **Stop Detection** — detaches from the flight; drone finishes landing on its own
4. **Detection History** tab — browse past sessions with pigeon count, detection image gallery, and MP4 recording

---

## Sensor Verification

On every flight, the system confirms all sensors are active before arming:

```
  SENSOR VERIFICATION — GPS-Denied Navigation
  [OK] EKF2_GPS_CTRL = 0   — GPS disabled
  [OK] EKF2_OF_CTRL  = 1   — Optical flow enabled
  [OK] SYS_HAS_GPS   = 0   — GPS hardware disabled

  Gazebo Sensor Topics
  [OK] Optical flow (MTF-01)
  [OK] Flow camera
  [OK] Downward rangefinder
  [OK] 2D lidar (RPLidar)
  [OK] Mono camera (Pi Cam)
```

---

## Pigeon Detection

A custom YOLOv8 model (`models/yolo/best_v4.pt`) detects pigeons live from the drone's camera during hover. The simulation world includes a pigeon billboard at hover height (2.5m), detected at ~89% confidence.

Detection images and a full flight video (takeoff → hover → landing) are saved per session and viewable in the web UI.

---

## Real Drone

The flight code uses MAVSDK — the same code runs on real hardware. Only the connection address changes:

```python
# Simulation
SYSTEM_ADDRESS = "udp://:14540"

# Real drone (companion computer → Pixhawk via USB)
SYSTEM_ADDRESS = "serial:///dev/ttyACM0:921600"
```

---

## Stopping the Simulation

```bash
pkill -f "gz sim"; pkill -x px4
```
