# shell

Bash scripts for launching and configuring the simulation environment.

## Files
- `launch.sh` — Main sim launcher: kills old PX4/gz processes, copies custom airframes+models+worlds (including `mono_cam_hd`) into `px4/Tools/simulation/gz/`, builds PX4 SITL, launches with selected world. Usage: `./scripts/shell/launch.sh [world_name] [--headless]` (default world: `indoor_room`). Must `source env.sh` first.
- `launch_with_stream.sh` — Headless-friendly launcher for sim + monitor stream. Enforces fixed-camera topic for monitoring (`fixed_cam`/`mono_cam_hd`) and never uses drone camera for monitor. Uses WebRTC by default (`STREAM_MODE=webrtc`) with auto-fallback to MJPEG if WebRTC dependencies are missing.
- `env.sh` — Sets environment variables for Gazebo/PX4 paths. Must be sourced before launch.sh: `source scripts/shell/env.sh`
- `_log.sh` — Shared logging helpers for shell scripts (colorized status and error output).
- `WINDOWS_AGENT_RUNBOOK.md` — WSL/Windows runbook for launching and debugging sim on Windows hosts.

## Tips
- Interactive PXH: set `SCARECROW_PXH_INTERACTIVE=1` when launching to keep `pxh>` interactive (skips FIFO injection).
- Cleanup stale processes when you see `Task already running`:
	```bash
	pkill -x px4 2>/dev/null || true
	pkill -f "gz sim" 2>/dev/null || true
	pkill -f mavsdk_server 2>/dev/null || true
	rm -f "$HOME/.px4/px4_lock-0" "$HOME/.px4/px4-sock-0"
	```
