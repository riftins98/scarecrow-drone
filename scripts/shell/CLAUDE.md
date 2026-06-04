# shell

Bash scripts for launching and configuring the simulation environment.

## Files
- `launch.sh` — Main sim launcher: kills old PX4/gz processes, copies custom airframes/server config, builds clean symlink mirrors for repo-owned models/worlds under `px4/build/` and PX4's Gazebo model/world folders, applies optional model overlays from `SCARECROW_MODEL_OVERLAY_DIR`, builds PX4 SITL, and launches the selected world. Falls back to the base `gz_holybro_x500` target when PX4 has not generated a world-specific target, while still passing `PX4_GZ_WORLD`. Accepts `world_name` or `world_name.sdf`. Usage: `./scripts/shell/launch.sh [world_name] [--headless]` (default world: `indoor_room`). Must `source env.sh` first.
- `launch_with_stream.sh` — Headless-friendly launcher for sim + monitor stream. Accepts `world_name` or `world_name.sdf` plus stream camera flags: `--fixed`, `--center`, `--drone_cam`, and `--drone_view` (`--drove_view` remains accepted as a typo alias). `--drone_cam` streams the drone's onboard camera; `--drone_view` generates a temporary `holybro_x500` model overlay with a collisionless chase camera mounted 1.5m behind and 0.5m above the drone, tilted 10 degrees downward. Defaults to 10 FPS for lower RTF impact unless `STREAM_FPS` is exported. Uses WebRTC by default (`STREAM_MODE=webrtc`) with auto-fallback to MJPEG only if WebRTC dependencies are missing; when multiple cameras are selected in WebRTC mode, the launcher uses the last selected camera as the live stream to keep PXH output clean. Provides world-specific default spawn poses for hangar pursuit worlds unless `PX4_GZ_MODEL_POSE` is explicitly set.
- `env.sh` — Sets environment variables for Gazebo/PX4 paths. Gazebo resources resolve from this repo's `worlds/` and `models/` directories, not PX4's copied simulation assets. Must be sourced before launch.sh: `source scripts/shell/env.sh`
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
