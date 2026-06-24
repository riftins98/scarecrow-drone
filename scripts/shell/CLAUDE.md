# shell

Bash scripts for launching and configuring the simulation environment.

## Files
- `launch.sh` — Main sim launcher: kills old PX4/gz processes, builds runtime-only symlink mirrors for repo-owned models/worlds under `px4/build/`, overlays Scarecrow airframes/config into the generated PX4 rootfs, resets stale PX4 params by default, builds the selected SITL target, and launches PX4 directly with `PX4_GZ_WORLD`. Optional `SCARECROW_MODEL_OVERLAY_DIR` is included in Gazebo resources for camera overlays. Accepts `world_name` or `world_name.sdf`. Usage: `./scripts/shell/launch.sh [world_name] [--headless]`. Must `source env.sh` first.
- `launch_with_stream.sh` — Headless-friendly launcher for sim + monitor stream. Accepts `world_name` or `world_name.sdf` plus stream camera flags: `--fixed`, `--center`, `--drone_cam`, and `--drone_view` (`--drove_view` remains accepted as a typo alias). `--drone_cam` streams the drone's onboard camera; `--drone_view` generates a temporary `holybro_x500` model overlay with a collisionless chase camera mounted 1.5m behind and 0.5m above the drone, tilted 10 degrees downward. Defaults to 10 FPS for lower RTF impact unless `STREAM_FPS` is exported. Uses WebRTC by default (`STREAM_MODE=webrtc`) with auto-fallback to MJPEG only if WebRTC dependencies are missing; when multiple cameras are selected in WebRTC mode, the launcher uses the last selected camera. Stream worker commands are built with Bash arrays so Gazebo topic paths are passed as single arguments.
- `env.sh` — Sets environment variables for Gazebo/PX4 paths. Gazebo resources resolve from this repo's `worlds/` and `models/` plus PX4's stock Gazebo assets; server config resolves to this repo's `config/server.config`. Must be sourced before launch.sh: `source scripts/shell/env.sh`
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
