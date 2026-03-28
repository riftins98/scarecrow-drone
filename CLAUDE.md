# PX4 X500 Full Sensor Simulation — Setup Guide

## Project Goal

Simulate a Holybro X500 V2 drone with full sensor stack as a replacement for delayed hardware in a university final project. The simulation runs on an Ubuntu 24.04 ARM64 VM (UTM, Apple Virtualization) on a Mac M1.

### Sensor Stack

| Sensor | Simulation Model |
|---|---|
| Optical flow (MTF-01) | `optical_flow` |
| Downward rangefinder (TF-Luna) | `LW20` |
| 2D lidar (RPLidar A1M8) | `lidar_2d_v2` |
| Mono camera (Pi Camera 3) | `mono_cam` |

All sensors are combined into the composite model `x500_full`.

---

## Environment

- **Mac**: Apple Silicon M1, macOS — used for SSH control and MAVLink GCS only
- **VM**: UTM Ubuntu 24.04 ARM64, Apple Virtualization framework, 8GB RAM, 64GB disk
- **VM IP**: `192.168.64.9`, user `saae`, passwordless sudo
- **Shared folder**: Mac's `/Users/sriftin/PX4-Autopilot` is mounted in VM at `/media/px4/PX4-Autopilot` via VirtioFS

---

## Files Changed from Upstream PX4

| File | What Changed |
|---|---|
| `Tools/simulation/gz/models/x500_full/model.sdf` | **Created** — composite model with all sensors |
| `Tools/simulation/gz/models/x500_full/model.config` | **Created** — model metadata |
| `ROMFS/px4fmu_common/init.d-posix/airframes/4022_gz_x500_full` | **Created** — custom airframe (GPS disabled) |
| `src/modules/simulation/gz_bridge/server.config` | `libOpticalFlowSystem.so` enabled, `libGstCameraSystem.so` disabled |
| `src/modules/simulation/gz_bridge/CMakeLists.txt` | Removed hardcoded `GZ_IP=127.0.0.1` |
| `ROMFS/px4fmu_common/init.d-posix/px4-rc.gzsim` | Headless rendering path support |

---

## One-Time Setup (Already Done)

These steps are complete and do not need to be repeated unless starting from scratch.

### 1. VM Setup
- UTM VM created: Ubuntu 24.04 ARM64, Apple Virtualization, 8GB RAM, 64GB disk
- VirtioFS shared folder configured in UTM pointing to `/Users/sriftin/PX4-Autopilot`
- SSH key installed: `ssh-copy-id saae@192.168.64.9`
- Passwordless sudo configured

### 2. VirtioFS Auto-mount
Added to `/etc/fstab` in VM:
```
share /media/px4 virtiofs defaults 0 0
```

### 3. PX4 Dependencies
```bash
# Run inside VM
cd /media/px4/PX4-Autopilot
bash Tools/setup/ubuntu.sh --no-nuttx
```

### 4. Gazebo Harmonic
Installed in VM via apt (gz-sim 8.11.0).

### 5. PX4 Build
```bash
# Run inside VM
cd /media/px4/PX4-Autopilot
make px4_sitl gz_x500_full
```

### 6. Airframe Cache Sync
```bash
cp ROMFS/px4fmu_common/init.d-posix/airframes/4022_gz_x500_full \
   build/px4_sitl_default/etc/init.d-posix/airframes/
```

---

## Every-Session Launch (3 Steps, In Order)

Open 3 terminals **inside the VM** (not SSH — use the UTM window directly).

### Before Starting — Check VirtioFS is Mounted
```bash
ls /media/px4/PX4-Autopilot/Tools/simulation/gz/worlds/default.sdf
```
If empty, mount it:
```bash
sudo mount -t virtiofs share /media/px4
```

### Terminal 1 — Gazebo Server
```bash
cd /media/px4/PX4-Autopilot && \
GZ_SIM_RESOURCE_PATH=/media/px4/PX4-Autopilot/Tools/simulation/gz/models:/media/px4/PX4-Autopilot/Tools/simulation/gz/worlds \
gz sim -v 4 -s Tools/simulation/gz/worlds/default.sdf
```

Wait until you see:
```
[Msg] Serving scene information on [/world/default/scene/info]
```

### Terminal 2 — Gazebo GUI
```bash
gz sim -v 4 -g
```

Wait for the Gazebo window to open and show the ground plane.

### Terminal 3 — PX4 SITL
```bash
cd /media/px4/PX4-Autopilot && \
source build/px4_sitl_default/rootfs/gz_env.sh && \
cp ROMFS/px4fmu_common/init.d-posix/airframes/4022_gz_x500_full \
   build/px4_sitl_default/etc/init.d-posix/airframes/ && \
PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=default make px4_sitl gz_x500_full
```

Wait until you see:
```
INFO  [init] Spawning Gazebo model
INFO  [gz_bridge] world: default, model: x500_full_0
INFO  [px4] Startup script returned successfully
```

**Then press ▶ play in the Gazebo GUI.** The drone (`x500_full_0`) will appear in the 3D viewport and Entity Tree.

---

## Validation

```bash
# From Mac terminal — verify all sensor topics are publishing
ssh saae@192.168.64.9 'gz topic -l | grep x500_full_0'
```

Expected output includes: `optical_flow`, `lidar`, `lidar_2d_v2`, `imu`, `air_pressure`, `navsat`, `magnetometer`, `camera_imu`.

---

## MAVLink Control from Mac

PX4 MAVLink is on VM port `18570`. To control from Mac:

```bash
# Enable broadcast so Mac can receive heartbeats
ssh saae@192.168.64.9 'cd /media/px4/PX4-Autopilot/build/px4_sitl_default && \
  ./bin/px4-param --instance 0 set MAV_0_BROADCAST 1 && \
  ./bin/px4-param --instance 0 set MAV_1_BROADCAST 1'
```

Then connect QGroundControl on Mac — it will auto-discover the drone.

Or with MAVSDK-Python:
```python
await drone.connect(system_address='udp://192.168.64.9:18570')
```

---

## Kill Everything
```bash
# From Mac terminal
ssh saae@192.168.64.9 'ps aux | grep -E "gz sim|bin/px4" | grep -v grep | awk "{print \$2}" | xargs -r kill -9'
```

Or press `Ctrl+C` in Terminal 3, then 2, then 1.

---

## Key Facts / Lessons Learned

- **Spawn vs attach mode**: `PX4_GZ_MODEL_NAME` must NOT be set — if set, PX4 tries to attach to an existing model instead of spawning one. Without it, PX4 spawns the drone correctly.
- **`gz_env.sh` must be sourced**: Without it, `PX4_GZ_MODELS` is unset and the spawn URI becomes `file:///x500_full/model.sdf` (broken). Source it before running make.
- **Single server instance**: Only one `gz sim -s` must run. Multiple instances cause the GUI to connect to the wrong server.
- **VirtioFS mount**: Does not auto-mount after reboot unless added to `/etc/fstab`. Check before each session.
- **GUI must run from inside VM**: Launching GUI via SSH fails because SSH sessions don't have proper access to the desktop GL context. Open terminals directly in the UTM window.
- **Docker approach abandoned**: Docker on macOS cannot run Gazebo GUI due to gz-transport multicast networking and GL rendering limitations on Apple Silicon.
