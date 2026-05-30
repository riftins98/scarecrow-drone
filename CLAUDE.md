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
- `design-system/` — Visual design system for the webapp (see `design-system/CLAUDE.md`). Read `design-system/scarecrow/MASTER.md` before any UI work.
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

## Cross-Platform Compatibility (macOS + Windows)
All code, scripts, and tooling MUST work on both macOS and Windows. The team has devs on both OSes.
- Python: avoid `os.fork`, POSIX-only modules, hardcoded `/tmp` or `/usr/local` paths — use `pathlib`, `tempfile.gettempdir()`, `os.path.join`.
- Shell scripts: bash scripts (`.sh`) must run under WSL on Windows. When adding a new `.sh` script, ensure it works under WSL (LF line endings, no Mac-only flags like BSD `sed`/`ps` quirks). Prefer Python over bash for new tooling when feasible.
- Paths: never hardcode `/Users/...` or `C:\...` — read from env vars or repo-relative paths.
- Subprocess invocations: use `python3` (works in both WSL and macOS), not `python`.
- Browser/network: bind to `0.0.0.0` (not `127.0.0.1` only) so WSL→Windows host browser access works.
- When in doubt, document in the relevant sub-CLAUDE.md whether a workflow is "WSL on Windows" or "native on both".

## Recent Changes
- Added a **panic RESET button** (red, full-width, in `SimControl`, always available while connected): `POST /api/sim/reset` hard-kills the flight script (`DetectionService.kill()`), force-disarms via MAVSDK (`DroneService.force_disarm()` → `action.kill()`), and teleports the Gazebo drone back to its spawn pose (`SimService.reset_drone_pose()` → world `set_pose` service; spawn = `SPAWN_POSE` constant `5,-4.5,0,0,0,0`, also fed to the launcher). Each step is best-effort. Integration-tested in `tests/integration/test_sim_api.py`.
- Removed the Gazebo RTF (real_time_factor) telemetry gauge end to end (inconsistent / looked bad): deleted the `gz topic -e -t /stats` poller + `rtf` property in `sim_service.py`, the `rtf` key in the sim status DTO, and `simStatus.rtf` in the frontend type. Replaced it with a **flight-log parser**: `DetectionService._parse_log_extras()` mines flight-script stdout (across all scripts) for `phase`, `agl`, `ceiling`, `leg`, lidar distances (`front`/`left`/`right`/`rear`/`wall`), commanded velocities (`fwd`/`lat`/`yaw`), pursuit `target`/`target_dist`, wall-follow `stop_reason`, and `fps`, merging them into `latest_telemetry`. Pure parser unit-tested in `tests/unit/webapp/services/test_detection_log_parser.py`. The `TelemetryRail` is now **dynamic** — it renders only the readouts the running script produces. HudHeader's RTF indicator light became a DETS light.
- Webapp UI overhauled into a military / HUD console: top `HudHeader` (callsign, system-state pill, local clock, indicator lights), scrolling `Ticker`, dynamic `TelemetryRail` (log-parsed gauges + GPS-DENIED badge), vertical `Sidebar` (OPS / DIAGNOSTICS), `Minimap` (top-down garage with obstacle-avoiding drone path), and full-width `SystemLog` (terminal-style mock feed). All in `webapp/frontend/src/components/`.
- Design system established at `design-system/scarecrow/MASTER.md`. UI work should read it first; future sessions stay visually consistent.
- `ui-ux-pro-max` skill installed at `.claude/skills/ui-ux-pro-max/`. Python `python3` shim at `~/.local/bin/python3.bat` is required on Windows.
- Webapp launcher: live per-step substatus (`Compiling [N/1157] ...`, EKF state, etc.) so users see actual progress rather than just "active".
- Backend: `SimService.launch(world, headless)` captures stream URL from `launch_with_stream.sh`; `DetectionService.start()` accepts script name + arg dict; `script_metadata.py` introspects flight scripts via `--help` for the dynamic pre-flight argparse form.
- `Start Scarecrow.bat` rewritten: auto-installs backend deps, hard-fails if backend doesn't respond, `-d`/`--dev` flag for visible log windows.
- Drone class honors `MAVSDK_SERVER_ADDRESS` / `MAVSDK_SERVER_PORT` env vars so flight scripts can connect to an externally-launched `mavsdk_server` for debugging.
