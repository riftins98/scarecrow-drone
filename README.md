# Scarecrow Drone

Autonomous indoor drone navigation **without GPS**, with live pigeon detection
and pursuit. Holybro X500 V2 on PX4 SITL and Gazebo Harmonic, with a web
console for launching and flying it.

Final-year project. The same flight code is written to run on the real
aircraft — see [Running on real hardware](#running-on-real-hardware).

---

## What it does

The drone flies a **circuit of an aircraft hangar**, following the walls at a
set distance using only its 2D lidar for position and optical flow for
velocity. There is no GPS and no external positioning.

While it flies, a YOLOv8 detector watches the forward camera. On a confident
pigeon detection the drone:

1. plans an approach from the target's position in the image,
2. breaks off the leg and yaws onto the target,
3. pursues it to a set stand-off distance,
4. returns to **exactly where it broke off**, restores its heading,
5. and resumes the interrupted leg.

At the end it lands and writes an annotated map of everything it saw.

A web console does the whole thing in one page: pick the world, camera and
start position, press Connect to launch the simulator, then fly — with live
video, telemetry and the flight log on screen.

---

## How it works

The problem is state estimation. Indoors there is no GPS, so the drone has to
answer "where am I and how fast am I moving?" from onboard sensors alone.

```
  optical flow  ──┐
  down rangefinder ├──►  PX4 EKF  ──►  velocity + attitude + height
  barometer, IMU ──┘                          │
                                              ▼
  2D lidar  ──────────────────────►  wall-follow / corner / pursuit
                                     controllers  (scarecrow/controllers/)
                                              │
  camera ──► YOLOv8 ──► target tracker ───────┤
                                              ▼
                                     mission  (scarecrow/missions/)
                                              │
                                              ▼
                                   MAVSDK offboard velocity ──► PX4
```

Two things are worth understanding before reading the code:

**The EKF gives velocity, the lidar gives position.** Optical flow tells PX4
how fast the drone is moving, but nothing tells it where it is in the room.
Position comes from the lidar — distance to the wall being followed is the
controlled variable. Where the two disagree, the lidar is right.

**Rotation temporarily breaks the estimate.** Turning a corner contaminates
optical flow with rotational motion, and the EKF needs several seconds to
recover. The mission handles this by holding still after each turn before
correcting position, rather than by tuning a controller. This is documented in
[`scarecrow/controllers/CLAUDE.md`](scarecrow/controllers/CLAUDE.md) with the
measurements behind it.

### Sensors

| Sensor | Hardware | Simulation model | Role |
|---|---|---|---|
| Optical flow | MTF-01 | `optical_flow` | Horizontal velocity → EKF |
| Down rangefinder | TF-Luna | `LW20` | Height correction → EKF |
| Up rangefinder | TF-Luna | `tf_luna_up` (100 Hz) | Ceiling clearance |
| 2D lidar | RPLidar A1M8 | `lidar_2d_v2` (5.5 Hz) | Wall following, obstacles, position |
| Forward camera | Pi Camera 3 | `mono_cam` (1280×720, 15 Hz) | YOLOv8 detection |
| Monitor camera | — | `mono_cam_hd` (1920×1080, 6 Hz) | Operator video only, not a flight input |

Simulated sensor rates match the real hardware deliberately, so a timing
assumption that breaks on the drone breaks in simulation first.

---

## Quick start

Pick by operating system. The two environments do not overlap, and the wrong
one wastes your time.

### Windows / Linux — Docker

The whole product in one container.

**On Windows, work inside WSL2 — not PowerShell.** `docker/build.sh` is a bash
script PowerShell cannot run, and the Windows GPU path passes through
`/dev/dxg` and `/usr/lib/wsl`, which are WSL2's own GPU device and driver
libraries.

**Which Docker you install depends on your GPU**, and getting this wrong is the
single most likely way to end up running the simulator on the CPU without
noticing:

| GPU | Which Docker to install |
|---|---|
| **NVIDIA** | Docker Desktop, with WSL Integration enabled for your distro |
| **AMD or Intel** | Docker Engine installed **natively inside the WSL2 distro** |

Docker Desktop's WSL2 backend forwards only NVIDIA devices, so on an AMD or
Intel laptop `/dev/dxg` will not exist inside the container and the GPU is
simply absent. Installing Docker Engine inside Ubuntu-on-WSL2 (the normal
`apt` install, no Docker Desktop) is what makes that path work.

```bash
# inside WSL2 (Ubuntu). Clone into the WSL filesystem, NOT /mnt/c —
# cross-filesystem I/O is dramatically slower.
git clone --recurse-submodules <repo-url> ~/scarecrow-drone
cd ~/scarecrow-drone

bash docker/build.sh       # builds the image, then detects your GPU and
                           # records it in .env
docker compose up          # → http://localhost:8000/
```

**You do not pick a GPU setting.** `build.sh` runs `docker/detect-gpu.sh`,
which looks for an NVIDIA runtime, then `/dev/dxg`, then `/dev/dri`, and writes
the matching overlay into `.env`. Compose reads that automatically, so a bare
`docker compose up` is already correct for the machine — and it says out loud
what it found, so a machine that has a GPU the container cannot see tells you
so instead of quietly running on the CPU.

Re-run it by hand any time the situation changes:

```bash
bash docker/detect-gpu.sh          # detect and record
bash docker/detect-gpu.sh --print  # just show what it would use
```

Run `bash docker/verify-delivery.sh` before trusting any of it — it exercises
the same detection and then proves the GPU actually renders, rather than
leaving you to infer it from how slow the simulation feels.

**AMD and Intel machines get CPU-only YOLO.** Gazebo renders on the GPU, but
PyTorch has no backend for those cards on Windows, so pigeon detection runs on
the processor. It works; it is just slow. Only NVIDIA and Apple accelerate it.

See [`docker/CLAUDE.md`](docker/CLAUDE.md) for the GPU traps, each of which
otherwise ships as "the simulator is mysteriously slow" with no error anywhere.

### macOS — pixi

Docker Desktop on macOS exposes no GPU at all, so macOS runs natively.
**Do not `brew install` the simulation dependencies** — a Homebrew upgrade
silently broke the entire build once, which is why the toolchain is pinned.

```bash
git clone --recurse-submodules <repo-url>
cd scarecrow-drone

pixi install        # materialise the locked environment
pixi run build      # build PX4 SITL (once)
pixi run webapp     # backend :8000 + frontend :3000
```

Then press **Connect** in the browser.

Other tasks: `pixi run sim` (headless simulator + video stream on :8080),
`pixi run fly` (the mission), `pixi run sensors` (diagnostics, no flight),
`pixi run test`.

The first launch after a build takes a few minutes; later launches are quick.

---

## Verify it works

Two checks, answering different questions. Run both on the machine that will
actually be used.

```bash
bash docker/verify-delivery.sh
```

Checks that **this machine** can run it: rendering, GPU path, the video
stream, and a real flight. `--no-gpu` skips the GPU checks.

Then [`docs/ACCEPTANCE_CHECKLIST.md`](docs/ACCEPTANCE_CHECKLIST.md) — the
manual pass, covering what only a person watching a full mission can judge:
whether the drone flies *well*, not merely whether it flies.

---

## Known limitations

Read [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) before relying on
anything. The short version: the hardware sensor drivers have never run on a
real drone, the amd64 image and GPU passthrough have never been exercised on
target hardware, and a handful of flight behaviours are known-thin rather than
finished.

---

## Repository layout

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) is the map: what processes run,
what talks to what, and how the layers stack.

Each directory also has a `CLAUDE.md` describing what is in it and why it is
built that way. Read the one for the area you are working in — that is where
the reasoning lives, including which apparently-arbitrary choices are
load-bearing.

| | |
|---|---|
| `scarecrow/` | The Python package: controllers, sensors, detection, navigation, missions. Installable, so the same code can run on a Raspberry Pi. |
| `scripts/flight/` | Entry points only. The missions live in `scarecrow/missions/`. |
| `scripts/shell/` | Simulator launch scripts |
| `webapp/` | FastAPI backend + React console |
| `models/`, `worlds/` | Gazebo models and hangar worlds |
| `docker/` | Delivery image for Windows/Linux |
| `tests/` | 561 tests — `pixi run test` |
| `docs/` | Acceptance checklist, limitations, user guides |
| `px4/` | PX4-Autopilot submodule — do not edit |

---

## Guides

Step-by-step walkthroughs with screenshots live in
[`docs/guides/`](docs/guides/README.md):

- [Simulation from the command line](docs/guides/simulation-cli.md) — no webapp
- [Webapp user guide](docs/guides/simulation-webapp.md) — the HUD console

---

## Running on real hardware

The flight code talks to the autopilot over MAVSDK, so only the connection
address changes:

```python
SYSTEM_ADDRESS = "udp://:14540"                    # simulation
SYSTEM_ADDRESS = "serial:///dev/ttyACM0:921600"    # companion computer → Pixhawk
```

`scarecrow/platform/` is the seam that makes this work: mission code depends on
a `SensorSuite`, never on Gazebo, and each simulated sensor has a hardware
driver behind the same interface.

**None of it has flown.** [`docs/HARDWARE_BRINGUP.md`](docs/HARDWARE_BRINGUP.md)
is the bring-up order — sensor by sensor, on the ground, props off — and
[`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) lists what is known
thin before you start.

---

## Development

```bash
pixi run test                    # full suite
pixi run verify-isolation        # assert PX4 linked pixi's Gazebo, not Homebrew's
```

Dependencies are declared in four places, because each answers a different
question — `requirements.txt` (the pinned reference), `pyproject.toml` (the
installable package), `pixi.toml` (the macOS environment) and
`docker/Dockerfile` (the delivery image). `tests/unit/test_dependency_pins.py`
asserts they agree; change a version in one and it will tell you which others
you missed.

---

## Usage

<!-- Confirm the exact wording with your project supervisor before handover. -->

Academic final project. Copyright remains with the author and the institution
under university policy. Provided to the recipient for their own use; no other
licence is granted.

Third-party components keep their own licences — PX4 (BSD-3-Clause), Gazebo
(Apache-2.0), and Ultralytics YOLOv8 (**AGPL-3.0**, which carries obligations
when software is redistributed).
