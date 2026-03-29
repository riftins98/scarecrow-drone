# Scarecrow Drone

Autonomous GPS-denied indoor drone simulation — Holybro X500 V2 with full sensor stack, powered by PX4 SITL and Gazebo Harmonic.

University final project: proves indoor flight using only optical flow + rangefinder for state estimation, with no GPS dependency.

## Sensor Stack

| Sensor | Hardware | Gazebo Model | Role |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity |
| Downward rangefinder | TF-Luna | `LW20` / `gpu_lidar` | Height estimation |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance |
| Mono camera | Pi Camera 3 | `mono_cam` | Visual awareness |

GPS is disabled — the drone navigates indoors using optical flow + rangefinder only.

## Repository Structure

```
scarecrow-drone/
├── airframes/4022_gz_holybro_x500   — PX4 airframe (GPS/baro disabled, flow+rangefinder)
├── config/server.config             — Gazebo server plugins (Sensors, OpticalFlow)
├── models/holybro_x500/model.sdf    — Composite drone model (x500 + all 4 sensors)
├── worlds/default.sdf               — Custom world with textured floor for optical flow
├── scripts/hover_test.py            — MAVSDK hover test (works on sim and real drone)
├── px4/                             — PX4-Autopilot submodule (branch: scarecrow)
└── .venv-mavsdk/                    — Python venv with MAVSDK
```

## Prerequisites

- macOS (Apple Silicon) or Ubuntu 24.04
- Gazebo Harmonic (gz-sim 8.x)
- PX4 SITL build dependencies
- Python 3 with MAVSDK (`pip install mavsdk`)

## Quick Start

### 1. Clone

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone
```

### 2. Build PX4

```bash
cd px4
bash Tools/setup/ubuntu.sh --no-nuttx  # Linux only
make px4_sitl gz_holybro_x500
cd ..
```

### 3. Run (3 terminals)

**Terminal 1 — Gazebo:**
```bash
export SCARECROW_DIR=$(pwd)
export PX4_DIR=$SCARECROW_DIR/px4
export GZ_SIM_RESOURCE_PATH=$SCARECROW_DIR/models:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds
export GZ_SIM_SERVER_CONFIG_PATH=$PX4_DIR/src/modules/simulation/gz_bridge/server.config
export GZ_SIM_SYSTEM_PLUGIN_PATH=$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins
export GZ_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}')
export GZ_PARTITION=px4
cd $PX4_DIR
cp $SCARECROW_DIR/config/server.config src/modules/simulation/gz_bridge/
gz sim -v 4 -r -s $SCARECROW_DIR/worlds/default.sdf
```

**Terminal 2 — PX4 SITL:**
```bash
export SCARECROW_DIR=$(pwd)
export PX4_DIR=$SCARECROW_DIR/px4
export GZ_SIM_RESOURCE_PATH=$SCARECROW_DIR/models:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds
export GZ_SIM_SYSTEM_PLUGIN_PATH=$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins
export GZ_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I | awk '{print $1}')
export GZ_PARTITION=px4
cd $PX4_DIR
cp $SCARECROW_DIR/airframes/4022_gz_holybro_x500 ROMFS/px4fmu_common/init.d-posix/airframes/
cp $SCARECROW_DIR/airframes/4022_gz_holybro_x500 build/px4_sitl_default/etc/init.d-posix/airframes/
cp $SCARECROW_DIR/airframes/4022_gz_holybro_x500 build/px4_sitl_default/rootfs/etc/init.d-posix/airframes/
PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=default make px4_sitl gz_holybro_x500
```

Then in `pxh>`:
```
param set EKF2_BARO_CTRL 0
param set EKF2_OF_QMIN 0
ekf2 stop
ekf2 start
commander set_ekf_origin 0 0 0
commander set_heading 0
```

**Terminal 3 — Flight Test:**
```bash
cd scarecrow-drone
source .venv-mavsdk/bin/activate
python3 scripts/hover_test.py
```

## Hover Test Output

The test script verifies sensor configuration before flight:
```
=======================================================
  SENSOR VERIFICATION — GPS-Denied Navigation
=======================================================
  [OK] EKF2_GPS_CTRL = 0 — GPS disabled
  [OK] EKF2_BARO_CTRL = 0 — Barometer disabled for height
  [OK] EKF2_HGT_REF = 2 — Height reference = rangefinder
  [OK] EKF2_OF_CTRL = 1 — Optical flow enabled
  [OK] EKF2_RNG_CTRL = 1 — Rangefinder enabled

--- Gazebo Sensor Topics ---
  [OK] Optical flow (MTF-01)
  [OK] Flow camera
  [OK] Downward rangefinder
  [OK] 2D lidar (RPLidar)
  [OK] Mono camera (Pi Cam)
```

Then performs: arm → takeoff → hover → land, logging altitude throughout.

## Real Drone

The hover test script uses MAVSDK — the same code runs on the real drone. Only the connection string changes:

```python
# Simulation
SYSTEM_ADDRESS = "udp://:14540"

# Real drone (companion computer → Pixhawk via USB)
SYSTEM_ADDRESS = "serial:///dev/ttyACM0:921600"
```

## Kill Everything

```bash
pkill -f "gz sim"; pkill -x px4
sudo rm -f /tmp/px4_lock-0 /tmp/px4-sock-0  # if needed
```

## License

University project — private repository.
