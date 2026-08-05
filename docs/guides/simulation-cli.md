# Scarecrow Drone: Developer Guide (Command Line)

**Part 1 of 2.** Run the GPS-denied indoor simulation and the autonomous flight
missions from a terminal, without the web UI.

| | |
|---|---|
| **Platforms** | macOS, Windows (WSL2), Linux |
| **Next guide** | [Webapp user guide](simulation-webapp.md), Part 2 |

---

## 1. Introduction

Scarecrow Drone demonstrates autonomous **GPS-denied indoor flight**. A Holybro
X500 quadcopter is simulated in **PX4 SITL** and **Gazebo Harmonic**, using
optical flow and a downward rangefinder for velocity and height, and a 2D lidar
for position. There is no GPS and no external positioning.

During flight a **YOLOv8** model watches the forward camera. On a confident
pigeon detection the drone breaks off its circuit, pursues the target to a set
distance, returns to exactly where it broke off, and resumes the leg.

This guide covers:

1. Setting up the environment for your platform
2. Launching the simulator from a terminal
3. Running the flight scripts, each of which verifies a different capability
4. Finding the detection images, mission maps and other outputs
5. Shutting everything down cleanly

**Not covered here:** the web console (Part 2) and real-hardware deployment
([`docs/HARDWARE_BRINGUP.md`](../HARDWARE_BRINGUP.md)).

---

## 2. Setup

Two terminals cooperate. One keeps the simulator running, the other sends
flight commands over MAVSDK.

Pick the setup for your operating system. They do not overlap, and the wrong
one will waste your time.

### macOS: pixi

Docker Desktop on macOS exposes no GPU, so macOS runs natively through
[pixi](https://pixi.sh), which pins the whole toolchain.

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone

pixi install        # materialise the locked environment
pixi run build      # build PX4 SITL, once
```

> **Do not `brew install` the simulation dependencies.** A `brew upgrade`
> silently broke the entire build once: protobuf moved, assimp was removed,
> nothing in the repository had changed, and Gazebo would not start at all.
> Homebrew has no lockfile. That is why pixi is here, and installing Gazebo or
> OpenCV through Homebrew alongside it reintroduces the same failure.

### Windows and Linux: Docker

The whole product in one container. **On Windows, work inside WSL2**, not
PowerShell: the scripts are bash, and the Windows GPU path uses WSL2 devices.

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git ~/scarecrow-drone
cd ~/scarecrow-drone

bash docker/build.sh    # builds the image, then detects your GPU
```

`build.sh` runs `docker/detect-gpu.sh`, which records the right GPU
configuration so later commands need no flags. It prints what it found, so a
machine whose GPU the container cannot reach says so rather than running slowly
in silence.

Clone into the WSL filesystem, not `/mnt/c`. Cross-filesystem I/O is far
slower.

### Legacy: virtualenv

The pre-Docker path, still supported on WSL and Linux.

```bash
python3.11 -m venv .venv        # 3.11 required, not 3.12+
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

cd px4 && bash Tools/setup/ubuntu.sh && cd ..
sudo apt install ffmpeg
```

---

## 3. Launch the simulator

Keep this terminal open for the whole session. Pass the world name that matches
the mission you intend to run.

Available worlds: `hangar`, `hangar_detailed`, `hangar_lite`, `hangar_small`.

### Headless with a browser stream

The default, and the right choice for demonstrations and for WSL. No Gazebo
window; the camera feeds are served to a browser instead.

```bash
pixi run sim                                  # macOS
bash docker/sim.sh sim --headless --fixed     # Windows and Linux
```

Open `http://localhost:8080/` for the camera stream.

To choose a different world or camera, pass the launcher's own flags:

```bash
bash docker/sim.sh sim --headless --fixed hangar_lite
```

![Browser stream viewer at localhost:8080](images/04-stream-viewer.png)

### With the Gazebo window

Best for live 3D demonstrations, on a machine with a display.

```bash
pixi run launch hangar_lite         # macOS
bash docker/sim.sh sim --fixed      # Windows and Linux, needs a display
```

Omitting `--headless` is what asks for a window. In a container that also needs
a display the container can reach, which on Windows means WSLg. Without one,
Gazebo cannot open a window.

The first launch after a build is slow, because PX4 relinks. Later launches are
quick.

### Camera flags

| Flag | Camera |
|---|---|
| `--fixed` | Static observer outside the transparent south wall, looking across the hangar. The default. |
| `--center` | Second static observer high in the arena, giving a top-side angle over the interior. |
| `--drone_cam` | The forward-facing camera on the drone itself. This is the flight and detection camera. |
| `--drone_view` | Chase camera following the drone for a third-person view. Useful for watching wall-following and pursuit. |

More than one may be given; the stream serves them together.

---

## 4. Run a flight mission

Open a second terminal and leave the simulator running in the first.

```bash
pixi run fly                    # macOS
bash docker/sim.sh fly          # Windows and Linux
```

Both run `hangar_circuit_pursuit.py`, the full mission. The other scripts run
the same way with the script name substituted.

### The three flight scripts

| Script | What it verifies |
|---|---|
| `sensor_check.py` | Lidar, camera, optical flow and rangefinder. No takeoff. Run this first when something looks wrong: it separates a sensor that is not publishing from a controller that is misbehaving. |
| `room_circuit_map.py` | A four-leg circuit that records the room boundary from lidar and writes a map. |
| `hangar_circuit_pursuit.py` | The full mission: circuit, live detection, pursuit, return to the break-off point, resume the leg, land, and write an annotated map. |

Run them in that order while learning the system, or go straight to the last.

### Mission options

Flags pass straight through and are identical on both platforms:

| Flag | Meaning |
|---|---|
| `--wall-distance` | Target distance from the followed wall during circuit legs. Default 2.0 m. |
| `--target-alt` | Explicit takeoff and hold altitude in metres above ground. |
| `--ceiling-clearance` | Minimum safe clearance to the ceiling. When given, takeoff altitude is derived from the upward rangefinder. |
| `--l` / `--r` | Which rear corner to stabilise against before the scan begins. Default left. |

```bash
pixi run fly --wall-distance 2.5 --target-alt 4.0
bash docker/sim.sh fly --wall-distance 2.5 --target-alt 4.0
```

> `--r` is **unverified**. Corner stabilisation currently uses the left wall
> regardless of this flag, so a right-hand circuit would stabilise against the
> wrong wall. See [`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md).

### What a good run looks like

- Takeoff to the commanded altitude, held without sagging
- Wall-follow legs tracking the target distance within roughly 0.15 m
- Each 90 degree turn ending aligned to the wall, followed by a deliberate
  three second pause before the drone corrects its position
- All four corners completed, then a controlled landing near the start

That pause is intentional. After a rotation the position estimate is briefly
wrong, and the mission waits for it to recover rather than flying on bad
numbers. `scarecrow/controllers/CLAUDE.md` carries the measurements.

---

## 5. Where results are saved

`hangar_circuit_pursuit.py` writes everything under one directory per flight:

```
webapp/output/<flight_id>/
  detections/          PNG frames saved during pursuit
  map.json             the lidar mission map
  map_annotated.png    annotated map with the route and pursuit events
```

The flight ID is printed at startup. Open `map_annotated.png` to review the
path and where each detection happened.

The pigeon is **teleported** when a pursuit succeeds, not deleted. Removing a
model from a running Gazebo world crashes the server. On a real drone nothing
is removed at all: a bird that has been approached disperses on its own, which
is the point of the project.

---

## 6. Shut it down

Leaving processes running poisons the next run. A leaked `mavsdk_server` holds
the MAVLink port so the next flight cannot connect, and a half-stopped PX4
makes the next launch fail with an error naming the estimator rather than the
real cause.

```bash
bash docker/sim.sh down                 # Windows and Linux
```

On macOS, stop the simulator terminal, then confirm nothing survived:

```bash
pgrep -fl "px4|gz sim|mavsdk_server|stream_camera"
```

It should print nothing. If it does:

```bash
pkill -x px4; pkill -f "gz sim"; pkill -f mavsdk_server; pkill -f stream_camera
rm -f "$HOME/.px4/px4_lock-0" "$HOME/.px4/px4-sock-0"
```

---

## 7. If something fails

1. Read the PX4 console first. Most flight failures announce themselves there.
2. Run `sensor_check.py` before suspecting a controller, to confirm the sensor
   is publishing at all.
3. For anything that looks like a control problem, log commanded velocity
   beside actual velocity before changing a gain. On this project three
   plausible control-theory explanations were all wrong, and one log line found
   the real cause.
4. Confirm the environment is clean. Processes left from a previous run cause
   failures that look like code bugs.

[`docs/ACCEPTANCE_CHECKLIST.md`](../ACCEPTANCE_CHECKLIST.md) is the full manual
pass, and [`docs/KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md) lists what is
known thin, before you go looking for a bug that is already documented.
