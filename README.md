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

Two supported environments. Pick by operating system — they do not overlap, and
the wrong one will waste your time.

| OS | Use | Why |
|---|---|---|
| **macOS** | pixi | Full Metal GPU. Docker Desktop on macOS exposes no GPU at all — measured RTF 0.055 vs 0.87 native, which is unflyable. |
| **Windows / Linux** | Docker | One container, one URL, pinned toolchain. GPU passes through. |

Both run the *same* application code — the same backend, frontend and launch
scripts. Only the environment around them differs.

### macOS — pixi

Install [pixi](https://pixi.sh) once (`curl -fsSL https://pixi.sh/install.sh | bash`), then:

```bash
git clone --recurse-submodules https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone

pixi install        # locked environment, ~36s
pixi run build      # build PX4 SITL, ~90s (once)
pixi run webapp     # http://localhost:3000
```

> **Do not `brew install` the simulation dependencies.** On 2026-06-20 a single
> `brew upgrade` moved protobuf to 35 (breaking the PX4 `-Werror` build) and
> removed assimp entirely (Gazebo could not start). Nothing in the repo had
> changed. Homebrew has no lockfile; `pixi.lock` pins all 770 packages by exact
> version and build hash, so a developer six months from now gets the identical
> bytes. Earlier versions of this README told you to `brew install gz-sim8
> opencv qt@5` — that instruction caused the failure above and has been removed.

| task | what it does |
|---|---|
| `pixi run webapp` | Backend :8000 + React dev server :3000 (hot reload) |
| `pixi run webapp-prod` | Built UI + API on :8000 — the same shape the Docker image ships |
| `pixi run sim` | Headless sim + camera stream on :8080 |
| `pixi run fly` | Hangar circuit pursuit mission (needs `pixi run sim`) |
| `pixi run sensors` | Sensor diagnostics, no flight |
| `pixi run test` | Test suite |
| `pixi run verify-isolation` | Assert PX4 linked pixi's Gazebo, not Homebrew's |

**Timing:** the first sim launch after a build takes **~165 seconds** — PX4
regenerates its rootfs, params and model mirrors. Every launch after that is
**~22 seconds**. The first run is not hung.

### Windows / Linux — Docker

```bash
git clone https://github.com/riftins98/scarecrow-drone.git
cd scarecrow-drone

docker compose up          # -> http://localhost:8000/
```

That URL is the whole interface: pick the world, camera and drone spawn, press
**Connect** to launch PX4 + Gazebo, then fly. Nothing else to run, and no shell
in the container.

The UI is not reachable instantly — the container checks the renderer and runs
a Gazebo preflight first. `docker compose ps` reports `healthy` when it is
ready.

**Use a GPU profile.** Without one the sim renders every camera and lidar on
the CPU, which "works" but is far too slow to fly:

```bash
docker compose --profile gpu up        # NVIDIA (Windows/WSL2 or Linux)
docker compose --profile gpu-wsl up    # ANY GPU on Windows via WSL2 (AMD, Intel, NVIDIA)
docker compose --profile gpu-dri up    # AMD or Intel on native Linux
```

Each sets `REQUIRE_GPU=1`, so a profile that does not actually reach the GPU
**fails at startup with an explanation** instead of quietly running on CPU.

`gpu-wsl` needs Docker running *inside* the WSL2 distro — Docker Desktop only
forwards NVIDIA devices.

Building the image is a maintainer action (`bash docker/build.sh`, not
`docker compose build`). Customers run a prebuilt image and never compile.

### Linux native (legacy)

The pre-Docker path, still supported for development on Ubuntu 22.04/24.04:

```bash
cd px4 && bash Tools/setup/ubuntu.sh && cd ..
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
sudo apt install ffmpeg
```

**Requires Python 3.11** — not 3.12+ (torch/ultralytics compatibility).

---

## Verifying a Machine Before You Trust It

Two scripts, answering two different questions. Conflating them means debugging
the wrong thing — a missing driver and an unexposed GPU look identical from the
outside, because both end in software rendering.

```bash
# Is anything missing from the image?  No GPU required.
docker run --rm scarecrow-sim:dev /opt/scarecrow/docker/self-test.sh

# Does it actually work on THIS machine?  Run on the target hardware.
bash docker/verify-delivery.sh
```

`self-test.sh` checks every Mesa driver (and that its libraries resolve), the
EGL/GL stack, the Gazebo render plugin, libassimp, the PX4 binary,
`mavsdk_server`, every lazily-imported Python module, and the frontend build.
It also feeds the renderer guard **recorded output from real NVIDIA, AMD, Intel
and WSL machines**, so vendor classification is tested on hardware the
developer machine has never had.

`verify-delivery.sh` auto-detects the GPU path, runs the self-test first, then
checks the renderer, the UI, Connect, the camera stream and a real flight.
Exit 0 means ready to hand over. `--no-gpu` skips only the GPU checks.

---

## Validation Status

Honest state as of the last commit. **This has not been run on Windows, on
Linux, or on any GPU.**

| what | status | evidence |
|---|---|---|
| macOS via pixi | **Verified** | Cold install 36s + build 90s; RTF 0.87; pursuit mission flies; no Homebrew linkage (86 `@rpath` entries into `.pixi`) |
| Docker product flow | **Verified on arm64** | 15/15 delivery checks: UI served, Connect reached all 11 launch steps without rebuilding PX4, ~79 MJPEG frames in 8s, all four sensor groups OK |
| Image completeness | **Verified on arm64** | 43/43 self-test checks |
| Renderer guard | **Verified** | Correctly classifies RTX 5090/5080, AMD discrete + integrated, Intel Arc + integrated, and all three WSL d3d12 vendors; rejects llvmpipe, softpipe, lavapipe, SVGA3D and WSL's "Microsoft Basic Render Driver" |
| **amd64 image** | **NOT BUILT** | Must be built on an amd64 host; cross-building on Apple Silicon takes hours |
| **GPU rendering** | **NOT VERIFIED** | Impossible on macOS — Docker Desktop exposes no GPU |
| **Windows / Linux end-to-end** | **NOT VERIFIED** | No access to the hardware |

Before handing this to anyone, build the amd64 image on an amd64 machine and
run `bash docker/verify-delivery.sh` there. That run is what decides whether
the delivery works.

Three GPU traps are already handled, each of which otherwise ships as "the sim
is mysteriously slow" with no error anywhere — see `docker/CLAUDE.md`:
the NVIDIA toolkit's default capabilities excluding OpenGL, `glxinfo` needing
an X server the container does not have, and WSL falling back to Microsoft's
software adapter through the same driver a real GPU uses.

---

## Guides

Step-by-step user guides (with screenshots and optional Word export) live in [`docs/guides/`](docs/guides/README.md):

- **Part 1:** [Simulation from the command line](docs/guides/simulation-cli.md) — no webapp
- **Part 2:** [Webapp user guide](docs/guides/simulation-webapp.md) — HUD console for demos

---

## Running the Web UI

| environment | command | opens |
|---|---|---|
| macOS (dev) | `pixi run webapp` | `http://localhost:3000` |
| macOS (as shipped) | `pixi run webapp-prod` | `http://localhost:8000` |
| Windows / Linux | `docker compose up` | `http://localhost:8000` |
| Windows native (legacy) | double-click `webapp/Start Scarecrow.bat` | `http://localhost:3000` |

In the Docker and `webapp-prod` cases the backend serves the built React bundle
itself, so the UI and the API share one origin on one port. `pixi run webapp`
keeps the React dev server on :3000 for hot reload.

---

## Headless Sim + Interactive PXH

Use this when you want headless Gazebo with an interactive `pxh>` prompt:

```bash
source scripts/shell/env.sh
SCARECROW_PXH_INTERACTIVE=1 PX4_GZ_MODEL_POSE="5,-4.5,0,0,0,0" \
  scripts/shell/launch_with_stream.sh drone_garage_pigeon_3d --headless
```

In `pxh>`:

```
commander set_ekf_origin 0 0 0
commander set_heading 0
```

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

## Cleanup (Stale Processes)

If you see `Task already running` or repeated `ekf2 missing data`, clear stale processes:

```bash
pkill -x px4 2>/dev/null || true
pkill -f "gz sim" 2>/dev/null || true
pkill -f mavsdk_server 2>/dev/null || true
rm -f "$HOME/.px4/px4_lock-0" "$HOME/.px4/px4-sock-0"
```

## Wall Follow v2

New wall-follow script with robust front-wall detection (world-agnostic):

```bash
# macOS
pixi run python scripts/flight/wall_follow_v2.py --side left --wall-distance 2.0 --forward-speed 0.35

# Linux native
source .venv/bin/activate && python3 scripts/flight/wall_follow_v2.py --side left --wall-distance 2.0
```
