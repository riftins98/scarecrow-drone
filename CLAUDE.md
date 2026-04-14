# scarecrow-drone

<!-- manual -->
GPS-denied indoor navigation system for autonomous quadcopters. Combines lidar-based wall following, optical flow, YOLO pigeon detection, and PX4/Gazebo simulation.

**Repository**: https://github.com/riftins98/scarecrow-drone

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
<!-- /manual -->

## Directory Map

Read only the sub-CLAUDE.md for the area you're working in.

- `scarecrow/` — Python package: flight controllers, sensor interfaces, navigation (see `scarecrow/CLAUDE.md`)
- `scripts/` — Flight scripts and shell launch utilities (see `scripts/CLAUDE.md`)
- `webapp/` — Full-stack web application for flight monitoring (see `webapp/CLAUDE.md`)
- `models/` — Gazebo simulation models (drone, sensors, targets) (see `models/CLAUDE.md`)
- `worlds/` — Gazebo world SDF files (see `worlds/CLAUDE.md`)
- `airframes/` — PX4 airframe configurations (see `airframes/CLAUDE.md`)
- `config/` — Gazebo server configuration (see `config/CLAUDE.md`)
- `px4/` — PX4-Autopilot git submodule (do not edit directly)

## Root Files
- `pyproject.toml` — Python project config (deps: mavsdk, numpy; optional: opencv, rplidar)
- `.gitmodules` — Submodule reference to PX4-Autopilot fork
- `README` — Project readme
