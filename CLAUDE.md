# scarecrow-drone

GPS-denied indoor navigation system for autonomous quadcopters. Combines lidar-based wall following, optical flow, YOLO pigeon detection, and PX4/Gazebo simulation.

**Repository**: https://github.com/riftins98/scarecrow-drone

## Documentation map

- `README.md` — what it does, how it navigates, how to run it
- `docs/ARCHITECTURE.md` — processes, ports, layers, the mission state machine
- `docs/HARDWARE_BRINGUP.md` — simulator to real aircraft
- `docs/KNOWN_LIMITATIONS.md` — what has never run, and what is known thin
- `docs/ACCEPTANCE_CHECKLIST.md` — the manual flight pass
- `docs/guides/` — reviewer-facing walkthroughs
- per-directory `CLAUDE.md` — local detail and the reasoning behind it

## Verification

`docs/ACCEPTANCE_CHECKLIST.md` is the manual flight checklist — what only a
human watching a full mission can judge. Run it after any change to
controllers, sensors, missions or worlds. `docker/verify-delivery.sh` is its
automated counterpart and proves the *environment* works on target hardware.

## Key Technologies
- **PX4 Autopilot** + **Gazebo** for simulation
- **MAVSDK** (Python) for flight control
- **YOLOv8** for pigeon detection
- **FastAPI** backend + **React** frontend
- **SQLite** for flight history

## Development Workflows

**macOS — use pixi.** Never `brew install` the sim dependencies; a `brew upgrade`
on 2026-06-20 silently broke the whole build (see the header of `pixi.toml`).

```bash
pixi install          # materialise the locked environment
pixi run build        # build PX4 SITL (once)
pixi run webapp       # backend :8000 + frontend :3000 — Connect launches the sim
```
Other tasks: `pixi run sim` (headless sim + stream on :8080), `pixi run fly`,
`pixi run sensors`, `pixi run test`, `pixi run verify-isolation`.
The first sim launch after a build is slow (PX4 relinks); later launches are quick.

**Windows/Linux — Docker.** The whole product in one container:

```bash
docker compose up          # -> http://localhost:8000/
```
That URL is the entire interface: pick world/camera/spawn, press Connect to
launch PX4 + Gazebo, then fly. No shell in the container, no second port to
open.

**The user never picks a GPU setting.** `docker/detect-gpu.sh` (run by
`build.sh`) chooses among three overlay files — NVIDIA, any-GPU-on-WSL2, and
AMD/Intel-on-native-Linux — and writes `COMPOSE_FILE` into `.env`, so a bare
`docker compose up` is correct on any machine. The overlays modify the single
`sim` service rather than adding services, which is what stops two containers
competing for the published ports. On Windows this must run inside WSL2.

- Build with `bash docker/build.sh` (sources the pinned versions and prunes
  orphaned images); plain `docker compose build` produces `FROM ubuntu@`.
- `docker run --rm scarecrow-sim:dev /opt/scarecrow/docker/self-test.sh` proves
  nothing is missing from the image — no GPU needed.
- Before handing over, run `bash docker/verify-delivery.sh` **on the target
  machine**. It auto-detects the GPU path and checks rendering, the stream and
  a real flight. `--no-gpu` skips only the GPU checks.

See `docker/CLAUDE.md` for the GPU traps (driver capabilities, EGL vs glxinfo,
and WSL's software fallback).

**WSL/Windows native — venv.** The pre-Docker path, still supported.
- Launch sim: `source scripts/shell/env.sh && ./scripts/shell/launch.sh [world_name]`
- Run flights: `source .venv/bin/activate && python3 scripts/flight/<script>.py`
- Web app: `cd webapp && ./start.sh` (frontend :3000, backend :8000)

## Directory Map

Read only the sub-CLAUDE.md for the area you're working in.

- `scarecrow/` — Python package: flight controllers, sensor interfaces, detection, navigation (see `scarecrow/CLAUDE.md`)
- `scripts/` — Flight scripts and shell launch utilities (see `scripts/CLAUDE.md`)
- `webapp/` — Full-stack web application for flight monitoring (see `webapp/CLAUDE.md`)
- `models/` — Gazebo simulation models: drone, sensors, targets, YOLO weights (see `models/CLAUDE.md`)
- `worlds/` — Gazebo world SDF files (see `worlds/CLAUDE.md`)
- `tests/` — Pytest unit tests for controllers and repositories (see `tests/CLAUDE.md`)
- `design-system/` — Visual design system for the webapp (see `design-system/CLAUDE.md`). Read `design-system/scarecrow/MASTER.md` before any UI work.
- `airframes/` — PX4 airframe configurations
- `config/` — Gazebo server configuration
- `docker/` — Delivery image for Windows/Linux: webapp + sim in one container (see `docker/CLAUDE.md`)
- `docs/` — Architecture, hardware bring-up, known limitations, the acceptance checklist, and the reviewer-facing guides under `docs/guides/`
- `px4/` — PX4-Autopilot git submodule (do not edit directly)

## Root Files

Four files declare dependencies and each answers a different question, so none
can be deleted in favour of another. `tests/unit/test_dependency_pins.py`
asserts they agree.

- `requirements.txt` — The pinned reference. Versions live here, and the other two environments are checked against it.
- `pyproject.toml` — The `scarecrow` package itself: what `pip install -e ".[sim]"` needs on a Raspberry Pi. Deliberately unpinned — a library that pins `==` cannot be co-installed with anything.
- `pixi.toml` + `pixi.lock` — The macOS environment: the conda toolchain PX4 SITL builds against, plus the Python deps. **Commit both**; the lock is what makes it reproducible.
- `docker-compose.yml` — The Windows/Linux entry point (`docker compose up`). One service; the GPU variants are overlay files under `docker/`, selected by `docker/detect-gpu.sh`. The image itself is `docker/Dockerfile`.

- `.gitmodules` — Submodule reference to the PX4-Autopilot fork
- `README.md` — Project readme

## Key Constraints
- Camera frame parsing MUST happen after flight, not during (destabilizes drone)
- Optical flow needs 2.5m+ altitude for good feature tracking
- Never param set EKF2 at runtime (resets estimator, breaks optical flow)
- Stock x500_flow airframe defaults work — only disable GPS
- GStreamer is not used anywhere and is not installed in the delivery image. It is a pipeline framework, not a wire format, so adopting it would not make streaming cross-platform — and it is broken on macOS, so it would create an OS split rather than remove one. Post-flight video uses PNG+ffmpeg, though that path is currently unwired (see `scarecrow/sensors/camera/CLAUDE.md`).

## Cross-Platform Compatibility (macOS + Windows)
All code, scripts, and tooling MUST work on both macOS and Windows. The team has devs on both OSes.
- Python: avoid `os.fork`, POSIX-only modules, hardcoded `/tmp` or `/usr/local` paths — use `pathlib`, `tempfile.gettempdir()`, `os.path.join`.
- Shell scripts: bash scripts (`.sh`) must run under WSL on Windows. When adding a new `.sh` script, ensure it works under WSL (LF line endings, no Mac-only flags like BSD `sed`/`ps` quirks). Prefer Python over bash for new tooling when feasible.
- Paths: never hardcode `/Users/...` or `C:\...` — read from env vars or repo-relative paths.
- Subprocess invocations: use `python3` (works in both WSL and macOS), not `python`.
- Browser/network: bind to `0.0.0.0` (not `127.0.0.1` only) so WSL→Windows host browser access works.
- When in doubt, document in the relevant sub-CLAUDE.md whether a workflow is "WSL on Windows" or "native on both".

## How the code is arranged, and why

Two structural facts explain most of the layout. Both are recent, and code
written against the old shape will look wrong.

**Missions live in the package, not in scripts.** `scripts/flight/` holds three
files, and the delivery mission among them is a 66-line entry point: it parses
arguments and calls `HangarCircuitPursuitMission`. The mission itself is
`scarecrow/missions/hangar_circuit/`, split into config, CLI, phases and
reporting. It was previously a 2247-line script with a 1147-line `run()`, which
could not be imported, tested or reused. **Anything runnable, testable or
reusable belongs in `scarecrow/`**; a script is argument parsing plus an
`asyncio.run()`. Six scripts disappeared into the package this way.

**The package is installable and hardware-ready.** `scarecrow/` is a real
Python package (`pip install -e ".[sim]"`), because the same flight code is
meant to run on a Raspberry Pi. `scarecrow/platform/` is the seam: mission code
depends on a `SensorSuite`, never on Gazebo. Every simulated sensor has a
hardware counterpart behind the same interface — `lidar/rplidar.py`,
`rangefinder/tfluna.py`, `camera/picamera.py`. None has run on a real drone
yet; see `docs/KNOWN_LIMITATIONS.md`.

Two consequences worth knowing before changing anything:

- **Sensors subscribe in-process.** `scarecrow/sensors/gz_transport.py` holds
  `gz.transport13` subscriptions; the old `gz topic -e -n 1` CLI polling
  survives only as an automatic fallback for hosts without the bindings. The
  fallback is a fork+exec per sample and starves the simulator, and it engages
  **silently** — check `sensor.using_transport`.
- **Flight-script log wording is a wire format.** The webapp parses stdout with
  regexes to drive the live telemetry rail. Reformatting a status line removes
  a gauge from the operator's screen and raises no error anywhere. See
  `scripts/flight/CLAUDE.md` for the parsed lines.
