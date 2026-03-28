# Scarecrow Drone

Autonomous indoor drone simulation — Holybro X500 V2 with full sensor stack, powered by PX4 SITL and Gazebo Harmonic.

## Sensor Stack

| Sensor | Hardware | Simulation Model |
|---|---|---|
| Optical flow | MTF-01 | `optical_flow` |
| Downward rangefinder | TF-Luna | `LW20` |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` |
| Mono camera | Pi Camera 3 | `mono_cam` |

GPS is disabled — the drone operates fully indoors using optical flow + rangefinder for state estimation.

---

## Repository Structure

```
scarecrow-drone/
├── models/holybro_x500/      — Gazebo composite drone model (x500 + all sensors)
├── airframes/                — PX4 custom airframe definition (ID 4022)
├── config/server.config      — Gazebo physics + sensor plugin config
├── px4/                      — PX4-Autopilot (git submodule, scarecrow branch)
├── launch.sh                 — Simulation launcher script
└── CLAUDE.md                 — AI assistant context
```

---

## Prerequisites

- Ubuntu 24.04 (native or VM) with at least 8GB RAM
- Gazebo Harmonic (gz-sim 8.x)
- PX4 build dependencies

> **Mac (Apple Silicon) and Windows users:** PX4 + Gazebo cannot run natively. You must use a Ubuntu VM. See the setup guides below.

---

## VM Setup

### Mac (Apple Silicon — M1/M2/M3)

1. Install [UTM](https://mac.getutm.app)
2. Create a new VM:
   - Virtualize (not emulate) — requires Apple Silicon
   - OS: Linux
   - Architecture: ARM64
   - ISO: [Ubuntu 24.04 ARM64](https://ubuntu.com/download/server/arm)
   - RAM: 8GB minimum, CPU: 4 cores, Disk: 64GB
   - Enable **Apple Virtualization** framework
3. Install Ubuntu (default settings, create user `saae`)
4. In UTM settings → Sharing → add a shared folder pointing to your cloned `scarecrow-drone` directory
5. Inside the VM, add to `/etc/fstab` for auto-mount:
   ```
   share /media/px4 virtiofs defaults 0 0
   ```
   Then: `sudo mkdir -p /media/px4 && sudo mount -a`

### Windows

1. Install [VirtualBox](https://www.virtualbox.org) or [VMware Workstation Player](https://www.vmware.com/products/workstation-player.html)
2. Download [Ubuntu 24.04 x86_64 ISO](https://ubuntu.com/download/desktop)
3. Create VM: 8GB RAM, 4 cores, 64GB disk, enable 3D acceleration
4. Install Ubuntu
5. Set up a shared folder pointing to your cloned `scarecrow-drone` directory
6. Mount it inside the VM:
   ```bash
   sudo mkdir -p /media/px4
   sudo mount -t vboxsf scarecrow-drone /media/px4   # VirtualBox
   # or for VMware: sudo mount -t fuse.vmhgfs-fuse .host:/ /media/px4
   ```

---

## One-Time Setup (inside the Ubuntu VM)

```bash
# 1. Clone the repo (with submodules)
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone

# 2. Install PX4 dependencies
cd px4
bash Tools/setup/ubuntu.sh --no-nuttx

# 3. Install Gazebo Harmonic
sudo apt-get install -y gz-sim8

# 4. Build PX4
make px4_sitl gz_holybro_x500
cd ..
```

---

## Running the Simulation

Open 3 terminals inside the Ubuntu VM (not SSH):

**Terminal 1 — Gazebo Server:**
```bash
cd /path/to/scarecrow-drone
GZ_SIM_RESOURCE_PATH=models:px4/Tools/simulation/gz/models:px4/Tools/simulation/gz/worlds \
gz sim -v 4 -s px4/Tools/simulation/gz/worlds/default.sdf
```
Wait for: `[Msg] Serving scene information on [/world/default/scene/info]`

**Terminal 2 — Gazebo GUI:**
```bash
gz sim -v 4 -g
```
Wait for the Gazebo window to open.

**Terminal 3 — PX4 SITL:**
```bash
cd /path/to/scarecrow-drone
cp airframes/4022_gz_holybro_x500 px4/build/px4_sitl_default/etc/init.d-posix/airframes/
cp config/server.config px4/src/modules/simulation/gz_bridge/
PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=default make -C px4 px4_sitl gz_holybro_x500
```
Wait for: `INFO [px4] Startup script returned successfully`

Then press **▶ Play** in the Gazebo GUI. The drone `holybro_x500_0` will appear.

---

## Validate Sensors

```bash
gz topic -l | grep holybro_x500_0
```

Expected topics include: `optical_flow`, `lidar`, `lidar_2d_v2`, `imu`, `air_pressure`, `navsat`, `magnetometer`, `camera_imu`

---

## MAVLink Control

PX4 MAVLink is on port `18570`. Connect from your host machine:

**QGroundControl:** Auto-discovers the drone on UDP port 14550.

**MAVSDK-Python:**
```python
await drone.connect(system_address='udp://VM_IP:18570')
```

Enable broadcast so the host can receive heartbeats:
```bash
cd px4/build/px4_sitl_default
./bin/px4-param --instance 0 set MAV_0_BROADCAST 1
```

---

## Kill Everything

```bash
kill $(pgrep -f "gz sim"); kill $(pgrep -x px4)
```
