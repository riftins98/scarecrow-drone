# shell

Bash scripts for launching and configuring the simulation environment.

## Files
- `launch.sh` — Main sim launcher: kills old PX4/gz processes, copies custom airframes+models+worlds (including `mono_cam_hd`) into `px4/Tools/simulation/gz/`, builds PX4 SITL, launches with selected world. Usage: `./scripts/shell/launch.sh [world_name] [--headless]` (default world: `indoor_room`). Must `source env.sh` first.
- `launch_with_stream.sh` — Headless-friendly launcher for sim + monitor stream. Enforces fixed-camera topic for monitoring (`fixed_cam`/`mono_cam_hd`) and never uses drone camera for monitor. Uses WebRTC by default (`STREAM_MODE=webrtc`) with auto-fallback to MJPEG if WebRTC dependencies are missing. Headless mode is interactive by default (drops into pxh shell).
- `env.sh` — Sets environment variables for Gazebo/PX4 paths. Must be sourced before launch.sh: `source scripts/shell/env.sh`
- `_log.sh` — Shared structured logger sourced by other shell scripts. Provides `_log_init <prefix>`, `_log_event`, `_log_info/_warn/_error`, and `_log_timer_begin/_end`. Writes key=value lines to `output/logs/<prefix>_<ts>.log`.
- `WINDOWS_AGENT_RUNBOOK.md` — Manual runbook for an agent helping a Windows user launch the headless sim + fixed-camera stream when Gazebo GUI is unstable.
