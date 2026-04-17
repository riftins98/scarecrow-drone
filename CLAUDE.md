# scarecrow-drone

GPS-denied indoor navigation system for autonomous quadcopters. Combines lidar-based wall following, optical flow, YOLO pigeon detection, and PX4/Gazebo simulation.

**Repository**: https://github.com/riftins98/scarecrow-drone

## Implementation Plan

See `docs/implementation/README.md` for the phased plan to complete the ADD. Each phase is a self-contained document in `docs/implementation/phases/`.

## Key Technologies
- **PX4 Autopilot** + **Gazebo** for simulation
- **MAVSDK** (Python) for flight control
- **YOLOv8** for pigeon detection
- **FastAPI** backend + **React** frontend
- **SQLite** for flight history

## Development Workflows
- Launch sim: `source scripts/shell/env.sh && ./scripts/shell/launch.sh [world_name]`
- Run flights: `source .venv-mavsdk/bin/activate && python3 scripts/flight/<script>.py`
- Web app: `cd webapp && ./start.sh` (frontend :3000, backend :8000)
- Commit: use `/commit` skill — updates all CLAUDE.md files and commits with clean message

## Directory Map

Read only the sub-CLAUDE.md for the area you're working in.

- `scarecrow/` — Python package: flight controllers, sensor interfaces, detection, navigation (see `scarecrow/CLAUDE.md`)
- `scripts/` — Flight scripts and shell launch utilities (see `scripts/CLAUDE.md`)
- `webapp/` — Full-stack web application for flight monitoring (see `webapp/CLAUDE.md`)
- `models/` — Gazebo simulation models: drone, sensors, targets, YOLO weights (see `models/CLAUDE.md`)
- `worlds/` — Gazebo world SDF files (see `worlds/CLAUDE.md`)
- `tests/` — Pytest unit tests for controllers and repositories (see `tests/CLAUDE.md`)
- `airframes/` — PX4 airframe configurations
- `config/` — Gazebo server configuration
- `docs/` — Implementation plan and specs (see `docs/implementation/README.md`)
- `px4/` — PX4-Autopilot git submodule (do not edit directly)

## Root Files
- `pyproject.toml` — Python project config (deps: mavsdk, numpy; optional: opencv, rplidar)
- `.gitmodules` — Submodule reference to PX4-Autopilot fork
- `requirements.txt` — Python dependencies
- `README.md` — Project readme

## Key Constraints
- Camera frame parsing MUST happen after flight, not during (destabilizes drone)
- Optical flow needs 2.5m+ altitude for good feature tracking
- Never param set EKF2 at runtime (resets estimator, breaks optical flow)
- Stock x500_flow airframe defaults work — only disable GPS
- GStreamer broken on Mac — use PNG+ffmpeg workaround for video
