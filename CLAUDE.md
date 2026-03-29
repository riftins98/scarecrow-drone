# Scarecrow Drone — Full Project Context

## Project Goal

University final project: simulate a Holybro X500 V2 drone with full sensor stack for GPS-denied indoor flight. The simulation replaces delayed hardware and must prove **all sensors work** to get project approval. If the simulation works, the same flight code runs on the real drone.

### User's Sensor Philosophy (DO NOT CHANGE)

> "GPS and IMU and baro need to be disabled, only using the optical flow for height and the lidar for self-position."

### Sensor Stack (must match real hardware exactly)

| Sensor | Hardware | Gazebo Model | Purpose |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity estimation |
| Downward rangefinder | TF-Luna | `LW20` + `lidar_sensor_link` (gpu_lidar) | Height estimation |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` | Obstacle avoidance / self-position |
| Mono camera | Pi Camera 3 | `mono_cam` | Visual awareness |

GPS is disabled. Height comes from rangefinder only. Horizontal position from optical flow.

---

## Repository Structure

```
/Users/saar.raynw/Desktop/scarecrow-drone/
├── airframes/
│   └── 4022_gz_holybro_x500       ← custom airframe (GPS/baro disabled, flow+rangefinder)
├── config/
│   └── server.config              ← Gazebo server plugins (Sensors + OpticalFlowSystem)
├── models/
│   └── holybro_x500/
│       ├── model.config
│       └── model.sdf              ← composite model: x500 + optical_flow + LW20 + lidar_2d_v2 + mono_cam + downward gpu_lidar
├── worlds/
│   └── default.sdf               ← custom world with 10x10 checkerboard floor (optical flow needs texture)
├── scripts/
│   └── hover_test.py             ← MAVSDK hover test (same code runs on real drone)
├── px4/                           ← git submodule → riftins98/PX4-Autopilot branch `scarecrow`
├── .venv-mavsdk/                  ← Python venv with mavsdk package
└── CLAUDE.md                      ← this file
```

**GitHub**: `riftins98/scarecrow-drone` (private), user `riftins98`
**PX4 fork**: `riftins98/PX4-Autopilot`, branch `scarecrow`
**Airframe**: ID 4022, model name `holybro_x500`

---

## Environment

- **Machine**: Apple Silicon M1, macOS
- **Simulation runs natively on Mac** — VM was abandoned (virgl GPU crashes camera sensors)
- **Gazebo**: Harmonic gz-sim 8.11.0 via Homebrew, ogre2 renderer (Metal GPU)
- **PX4 SITL**: builds natively on Mac with SDK workaround (see below)
- **Python**: `.venv-mavsdk/` with MAVSDK-Python for flight control
- **Network IP**: `192.168.68.117` — verify with `ipconfig getifaddr en0` (may change between sessions)
- **GitHub CLI**: `gh auth` as `riftins98`

### macOS Build Workaround

macOS 26 has a broken SDK symlink. Required for every PX4 build:
```bash
export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.2.sdk
export CXXFLAGS="-cxx-isystem ${SDKROOT}/usr/include/c++/v1 -isysroot ${SDKROOT}"
export CMAKE_PREFIX_PATH="/opt/homebrew/opt/qt@5:$CMAKE_PREFIX_PATH"
```

### Stale File Ownership

Some `/tmp/px4_*` files may be owned by user `sriftin` (previous Mac user). Need `sudo rm` to clean:
```bash
sudo rm -f /tmp/px4_lock-0 /tmp/px4-sock-0
```

---

## EKF2 / Airframe Parameters

Defined in `airframes/4022_gz_holybro_x500`:

```sh
# GPS disabled
SYS_HAS_GPS 0, SIM_GPS_USED 0, EKF2_GPS_CTRL 0

# Optical flow + rangefinder navigation
EKF2_OF_CTRL 1       # optical flow fusion enabled
EKF2_RNG_CTRL 1      # rangefinder control enabled
EKF2_HGT_REF 2       # height reference = rangefinder (not baro)
EKF2_BARO_CTRL 0     # barometer disabled for height
EKF2_MAG_TYPE 5      # magnetometer disabled
SENS_MAG_MODE 0      # mag sensor disabled
SENS_IMU_MODE 1      # IMU voter mode

# Arming for GPS-denied autonomous sim
COM_RC_IN_MODE 1, COM_ARM_WO_GPS 1, COM_HOME_EN 0
NAV_DLL_ACT 0, NAV_RCL_ACT 0, MAV_0_BROADCAST 1
```

**IMPORTANT**: `EKF2_BARO_CTRL 0` and `EKF2_OF_QMIN 0` must be set at runtime with `param set` because `param set-default` in the airframe gets overridden by saved params. After setting, restart EKF2:
```
param set EKF2_BARO_CTRL 0
param set EKF2_OF_QMIN 0
ekf2 stop
ekf2 start
```

---

## Every-Session Launch (3 Terminals, all on Mac)

### Pre-launch cleanup
```bash
pkill -f "gz sim"; pkill -x px4; sleep 2
sudo rm -f /tmp/px4_lock-0 /tmp/px4-sock-0
```

### Terminal 1 — Gazebo Server

```bash
export SCARECROW_DIR=~/Desktop/scarecrow-drone
export PX4_DIR=$SCARECROW_DIR/px4
export GZ_SIM_RESOURCE_PATH=$SCARECROW_DIR/models:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds
export GZ_SIM_SERVER_CONFIG_PATH=$PX4_DIR/src/modules/simulation/gz_bridge/server.config
export GZ_SIM_SYSTEM_PLUGIN_PATH=$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins
export GZ_IP=192.168.68.117
export GZ_PARTITION=px4
cd $PX4_DIR
cp $SCARECROW_DIR/config/server.config src/modules/simulation/gz_bridge/
gz sim -v 4 -r -s $SCARECROW_DIR/worlds/default.sdf
```

Wait for: `Serving world controls`

**Key notes:**
- `-r` flag = run immediately (no GUI to press Play)
- `GZ_SIM_SYSTEM_PLUGIN_PATH` is required for `libOpticalFlowSystem.dylib`
- `server.config` filename in the plugin is `libOpticalFlowSystem` (no extension — works cross-platform)
- Custom world `worlds/default.sdf` has checkerboard floor for optical flow feature tracking

### Terminal 2 — PX4 SITL

```bash
export SCARECROW_DIR=~/Desktop/scarecrow-drone
export PX4_DIR=$SCARECROW_DIR/px4
export GZ_SIM_RESOURCE_PATH=$SCARECROW_DIR/models:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds
export GZ_SIM_SYSTEM_PLUGIN_PATH=$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins
export GZ_IP=192.168.68.117
export GZ_PARTITION=px4
export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.2.sdk
export CXXFLAGS="-cxx-isystem ${SDKROOT}/usr/include/c++/v1 -isysroot ${SDKROOT}"
export CMAKE_PREFIX_PATH="/opt/homebrew/opt/qt@5:$CMAKE_PREFIX_PATH"
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

### Terminal 3 — Flight Test

```bash
cd ~/Desktop/scarecrow-drone
source .venv-mavsdk/bin/activate
python3 scripts/hover_test.py
```

The script:
1. Verifies all 5 EKF2 params (GPS off, baro off, rangefinder height, flow enabled)
2. Checks all Gazebo sensor topics are publishing
3. Arms via MAVSDK offboard
4. Takes off, hovers, lands
5. Logs altitude throughout

---

## Files Changed from Upstream PX4

| File | Change |
|---|---|
| `models/holybro_x500/model.sdf` | Composite model: x500 + optical_flow + LW20 + lidar_2d_v2 + mono_cam + downward gpu_lidar |
| `airframes/4022_gz_holybro_x500` | Custom airframe: GPS/baro disabled, optical flow + rangefinder |
| `config/server.config` | `libOpticalFlowSystem` enabled, `gz-sim-sensors-system` with ogre2 |
| `worlds/default.sdf` | Custom world: 10x10 checkerboard floor for optical flow tracking |
| `px4/ROMFS/.../px4-rc.gzsim` | Added `sensors stop/start` after gz_bridge (fixes EKF2 init race) |
| `px4/src/.../GZMixingInterfaceESC.cpp` | float→double cast fix for Apple clang |
| `px4/src/.../gz_bridge/CMakeLists.txt` | Removed hardcoded `GZ_IP=127.0.0.1` |

---

## Current Status (2026-03-29)

### What Works
- All 5 Gazebo sensor topics publish: optical flow, flow camera, rangefinder, 2D lidar, mono camera
- EKF2 runs with correct flags: `cs_rng_hgt: True`, `cs_baro_hgt: False`, `cs_gps_hgt: False`
- Drone arms and takes off via MAVSDK offboard control
- Reached 0.835m altitude during test flight
- MAVSDK hover test verifies all params + sensor topics before flight
- `sensors stop/start` fix in px4-rc.gzsim resolves EKF2 init race condition (0 update events)
- Optical flow quality=255 on ground (checkerboard floor provides features)

### Open Issues (need fixing)

1. **Altitude oscillation**: drone reaches ~0.8m then drops, doesn't sustain target. Position controller needs tuning for rangefinder-only height (no baro damping). May need PID gains adjustment or position controller params.

2. **Optical flow not fusing in EKF2**: `cs_opt_flow` stays False during flight. Root cause analysis:
   - EKF2 needs `isTerrainEstimateValid() || isHorizontalAidingActive()` to start flow fusion (`optical_flow_control.cpp:158`)
   - Without horizontal aiding, falls to line 206: `isTerrainEstimateValid() || (_height_sensor_ref == HeightSensor::RANGE)`
   - `_height_sensor_ref` should be RANGE since `EKF2_HGT_REF=2` and `cs_rng_hgt=True`
   - But `cs_rng_terrain` is False (rangefinder used as height, not terrain — `stopRngTerrFusion()` called at `range_height_control.cpp:161/179`)
   - Possible timing issue: optical flow checks run before `_height_sensor_ref` is set
   - Also: `sensor_optical_flow` (raw from gz_bridge) shows `quality: 0` while `vehicle_optical_flow` (processed) shows `quality: 255` — inconsistency needs investigation

3. **`EKF2_BARO_CTRL 0` doesn't persist**: `param set-default` in airframe is overridden by PX4's saved params. Must use `param set` at runtime before every flight. To fix permanently: `param reset_all` then restart PX4 (but this resets ALL params).

---

## Optical Flow Architecture

```
Gazebo camera sensor (flow_camera, 100x100px, 50Hz)
  → publishes image topic
  → OpticalFlowSystem plugin (server.config) subscribes
  → computes optical flow (OpenCV feature tracking)
  → publishes gz optical_flow topic
  → gz_bridge (GZBridge.cpp:opticalFlowCallback) subscribes
  → publishes sensor_optical_flow uORB
  → VehicleOpticalFlow module processes
  → publishes vehicle_optical_flow uORB
  → EKF2 uses for velocity estimation (when cs_opt_flow=True)
```

The checkerboard floor in `worlds/default.sdf` provides visual features for the flow algorithm. Without it, the default flat gray ground produces quality=0.

## Rangefinder Architecture

```
gpu_lidar sensor in model.sdf (lidar_sensor_link, 1 ray, 50Hz)
  → publishes scan topic
  → gz_bridge (distanceSensorCallback) subscribes
  → publishes distance_sensor uORB
  → EKF2 uses for height (EKF2_HGT_REF=2)
```

---

## Key Rules (DO NOT VIOLATE)

1. **NO GPS** — do not enable `SIM_GPS_USED`, `EKF2_GPS_CTRL`, or add GPS to SDF
2. **NO barometer for height** — `EKF2_BARO_CTRL` must be 0
3. **NO VM** — virgl GPU crashes on camera sensors, simulation runs natively on Mac
4. **NO Gazebo GUI** — not needed, headless with `-r` flag
5. **NO `GZ_IP=127.0.0.1`** — breaks pub/sub (loopback doesn't support multicast)
6. **NO QGroundControl running** while PX4 is active — grabs port 18570
7. **Use MAVSDK-Python** for flight control — same code runs on real drone
8. **Use pymavlink only for low-level debugging** — not for flight control (offboard doesn't work reliably)
9. **`GZ_SIM_SYSTEM_PLUGIN_PATH`** must point to build plugins dir for OpticalFlowSystem
10. **`-r` flag** on `gz sim -s` — starts sim running without GUI
11. **Single `gz sim -s` instance** — never run two servers
12. **Always copy airframe + server.config** before launching PX4 (3 copy commands)

---

## Diagnostic Commands (in `pxh>`)

```bash
# EKF2 status (must show update events > 0)
ekf2 status

# Sensor fusion flags
listener estimator_status_flags

# Optical flow data
listener vehicle_optical_flow
listener sensor_optical_flow

# Rangefinder
listener distance_sensor

# IMU (should show z: ~-9.8)
listener sensor_accel

# Check what's blocking arming
listener failsafe_flags
listener health_report
commander check
```

## Gazebo Sensor Verification

```bash
export GZ_IP=192.168.68.117 GZ_PARTITION=px4
gz topic -l | grep holybro_x500_0
```

Expected topics include: `optical_flow`, `flow_camera/image`, `lidar/scan`, `lidar_2d_v2`, `camera`, `imu`, `air_pressure`, `magnetometer`
