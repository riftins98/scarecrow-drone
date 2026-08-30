# shell

Bash scripts for launching and configuring the simulation environment.

## Files
- `launch.sh` — Main sim launcher: kills old PX4/gz processes, builds runtime-only symlink mirrors for repo-owned models/worlds under `px4/build/`, overlays Scarecrow airframes/config into the generated PX4 rootfs, resets stale PX4 params by default, builds the selected SITL target, and launches PX4 directly with `PX4_GZ_WORLD`. Optional `SCARECROW_MODEL_OVERLAY_DIR` is included in Gazebo resources for camera overlays. Accepts `world_name` or `world_name.sdf`. Usage: `./scripts/shell/launch.sh [world_name] [--headless]`. Must `source env.sh` first. PX4 stdout is teed through `stdbuf -oL tee` so a parent that reads the pipe (the webapp Connect watcher) sees "Startup script returned" line-by-line instead of only when the process exits.
- `launch_with_stream.sh` — Headless-friendly launcher for sim + monitor stream. Accepts `world_name` or `world_name.sdf` plus stream camera flags: `--fixed`, `--center`, `--drone_cam`, and `--drone_view` (`--drove_view` remains accepted as a typo alias). `--drone_cam` streams the drone's onboard camera; `--drone_view` generates a temporary `holybro_x500` model overlay with a collisionless chase camera mounted 1.5m behind and 0.5m above the drone, tilted 10 degrees downward. Defaults to 5 FPS at JPEG quality 92 unless `STREAM_FPS`/`STREAM_QUALITY` are exported — the fixed camera is 1920x1080 and renders at 6Hz, so the stream is sized for sharpness rather than smoothness. Streams MJPEG via `scripts/stream_camera.py`; there is no other mode, and multiple selected cameras are all served from the one worker. Stream worker commands are built with Bash arrays so Gazebo topic paths are passed as single arguments.
- `env.sh` — Sets environment variables for Gazebo/PX4 paths. Gazebo resources resolve from this repo's `worlds/` and `models/` plus PX4's stock Gazebo assets; server config resolves to this repo's `config/server.config`. Must be sourced before launch.sh: `source scripts/shell/env.sh`
- `_log.sh` — Shared logging helpers for shell scripts (colorized status and error output).
- `world_meta.py` — Resolves world metadata from the SDF files themselves rather than a hardcoded registry: `world_meta.py default-world`, `world_meta.py spawn-pose <world_id>`. `launch_with_stream.sh` calls it, which is why the Docker image must copy `webapp/backend` — it loads `world_geometry.py` by absolute path.
- `verify_pixi_isolation.sh` — Asserts the PX4 build linked pixi's Gazebo and not Homebrew's (`pixi run verify-isolation`). Homebrew ships the *same* gz-transport13 13.5.0 conda-forge does, so if CMake picks Homebrew's copy the build succeeds, the sim runs, and the reproducible environment proves nothing — it is silently depending on whatever the developer happens to have installed. The build task passes `-DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew`; this checks it worked.

## Tips
- Interactive PXH: set `SCARECROW_PXH_INTERACTIVE=1` when launching to keep `pxh>` interactive (skips FIFO injection).
- Cleanup stale processes when you see `Task already running`:
	```bash
	pkill -x px4 2>/dev/null || true
	pkill -f "gz sim" 2>/dev/null || true
	pkill -f mavsdk_server 2>/dev/null || true
	rm -f "$HOME/.px4/px4_lock-0" "$HOME/.px4/px4-sock-0"
	```
