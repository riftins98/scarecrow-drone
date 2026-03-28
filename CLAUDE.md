# Scarecrow Drone — Project Context

## Project Goal

Simulate a Holybro X500 V2 drone with full sensor stack as a replacement for delayed hardware in a university final project. The simulation runs on an Ubuntu 24.04 ARM64 VM (UTM, Apple Virtualization) on a Mac M1.

### Sensor Stack

| Sensor | Hardware | Simulation Model |
|---|---|---|
| Optical flow | MTF-01 | `optical_flow` |
| Downward rangefinder | TF-Luna | `LW20` |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` |
| Mono camera | Pi Camera 3 | `mono_cam` |

GPS is disabled — indoor GPS-denied operation using optical flow + rangefinder.

---

## Repository Structure

- **Main repo**: `/Users/sriftin/scarecrow-drone` (GitHub: `riftins98/scarecrow-drone`, private)
- **PX4 submodule**: `scarecrow-drone/px4/` → `riftins98/PX4-Autopilot`, branch `scarecrow`
- **Drone model**: `holybro_x500` (airframe ID 4022, file `4022_gz_holybro_x500`)
- **Make target**: `make px4_sitl gz_holybro_x500`

---

## Environment

- **Mac**: Apple Silicon M1, macOS — SSH control and MAVLink GCS only
- **VM**: UTM Ubuntu 24.04 ARM64, Apple Virtualization, 8GB RAM, 64GB disk
- **VM IP**: `192.168.64.9`, user `saae`, passwordless sudo
- **Shared folder**: Mac's `/Users/sriftin/PX4-Autopilot` mounted in VM at `/media/px4/PX4-Autopilot` via VirtioFS

> Note: The VirtioFS share points to the old `/Users/sriftin/PX4-Autopilot` path (which is the px4 submodule contents). In the VM, PX4 lives at `/media/px4/PX4-Autopilot`.

---

## Files Changed from Upstream PX4

| File | What Changed |
|---|---|
| `models/holybro_x500/model.sdf` | **Created** — composite model (x500 + all sensors) |
| `models/holybro_x500/model.config` | **Created** — model metadata |
| `airframes/4022_gz_holybro_x500` | **Created** — custom airframe (GPS disabled) |
| `config/server.config` | `libOpticalFlowSystem.so` enabled, `libGstCameraSystem.so` disabled |
| `px4/src/modules/simulation/gz_bridge/CMakeLists.txt` | Removed hardcoded `GZ_IP=127.0.0.1` |
| `px4/ROMFS/px4fmu_common/init.d-posix/px4-rc.gzsim` | Headless rendering path support |

---

## One-Time Setup (Already Done)

### VM
- UTM VM: Ubuntu 24.04 ARM64, Apple Virtualization, 8GB RAM, 64GB disk
- VirtioFS shared folder: Mac `/Users/sriftin/PX4-Autopilot` → VM `/media/px4/PX4-Autopilot`
- SSH key installed, passwordless sudo configured
- `/etc/fstab` entry: `share /media/px4 virtiofs defaults 0 0`

### PX4
```bash
cd /media/px4/PX4-Autopilot
bash Tools/setup/ubuntu.sh --no-nuttx
make px4_sitl gz_holybro_x500
```

---

## Every-Session Launch (3 Terminals, inside VM)

Check VirtioFS is mounted first:
```bash
ls /media/px4/PX4-Autopilot/Tools/simulation/gz/worlds/default.sdf
# If empty: sudo mount -t virtiofs share /media/px4
```

**Terminal 1 — Gazebo Server:**
```bash
cd /media/px4/PX4-Autopilot
export GZ_SIM_RESOURCE_PATH=/Users/sriftin/scarecrow-drone/models:/media/px4/PX4-Autopilot/Tools/simulation/gz/models:/media/px4/PX4-Autopilot/Tools/simulation/gz/worlds
gz sim -v 4 -s Tools/simulation/gz/worlds/default.sdf
```
Wait for: `[Msg] Serving scene information on [/world/default/scene/info]`

**Terminal 2 — Gazebo GUI:**
```bash
gz sim -v 4 -g
```
Wait for Gazebo window to open, then press ▶ Play.

**Terminal 3 — PX4 SITL:**
```bash
cd /media/px4/PX4-Autopilot
cp /Users/sriftin/scarecrow-drone/airframes/4022_gz_holybro_x500 \
   ROMFS/px4fmu_common/init.d-posix/airframes/
cp /Users/sriftin/scarecrow-drone/airframes/4022_gz_holybro_x500 \
   build/px4_sitl_default/etc/init.d-posix/airframes/
cp /Users/sriftin/scarecrow-drone/config/server.config \
   src/modules/simulation/gz_bridge/
export GZ_SIM_RESOURCE_PATH=/Users/sriftin/scarecrow-drone/models:/media/px4/PX4-Autopilot/Tools/simulation/gz/models:/media/px4/PX4-Autopilot/Tools/simulation/gz/worlds
PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=default make px4_sitl gz_holybro_x500
```
Wait for: `INFO [px4] Startup script returned successfully`

> **Note on VirtioFS paths**: The VM currently mounts Mac's `/Users/sriftin/PX4-Autopilot` (the px4 submodule) at `/media/px4/PX4-Autopilot`. The scarecrow-drone repo itself (`/Users/sriftin/scarecrow-drone`) is on the Mac and accessible via the Mac path above when running from inside the VM via shared folder. `launch.sh` is the future single-command alternative once the full scarecrow-drone directory is mounted in the VM.

---

## Validation

```bash
gz topic -l | grep holybro_x500_0
```

---

## MAVLink from Mac

```bash
ssh saae@192.168.64.9 'cd /media/px4/PX4-Autopilot/build/px4_sitl_default && \
  ./bin/px4-param --instance 0 set MAV_0_BROADCAST 1'
# Then connect QGroundControl or: await drone.connect(system_address='udp://192.168.64.9:18570')
```

---

## Kill Everything

```bash
ssh saae@192.168.64.9 'kill $(pgrep -f "gz sim"); kill $(pgrep -x px4)'
```

---

## Key Facts

- **Model name**: `holybro_x500` (was `x500_full` — fully renamed)
- **Spawn mode**: `PX4_GZ_MODEL_NAME` must NOT be set
- **`gz_env.sh` must be sourced** or `GZ_SIM_RESOURCE_PATH` set manually
- **Single server instance**: only one `gz sim -s` must run
- **VirtioFS**: does not auto-mount after reboot unless in `/etc/fstab`
- **GUI rendering**: Ogre2 gray viewport is an unresolved issue in this VM — GUI opens but 3D scene may not render. PX4 and sensors work regardless.
- **Gazebo GUI must run from inside VM**: not via SSH
