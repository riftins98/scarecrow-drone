# Windows Agent Runbook: Headless Sim + Fixed-Camera Stream

This guide is for an agent helping a Windows user run the project when Gazebo GUI is unstable.

## Architecture Rules (Must Keep)
- Drone camera (`holybro_x500`) is for flight/detection logic only.
- Fixed camera (`fixed_cam` / `mono_cam_hd`) is for monitoring stream only.
- Never let flight scripts consume the fixed camera topic.

## Primary Goal
Keep PX4 + sensors stable in headless mode, while providing live monitor video.

## Standard Launch
From repo root:

```bash
./scripts/shell/launch_with_stream.sh --headless
```

Default behavior:
- Starts sim in headless mode
- Waits for drone topics
- Waits for fixed camera topic
- Starts stream server (`STREAM_MODE=webrtc` by default)
- Opens browser monitor

## Explicit Stream Modes
WebRTC preferred:

```bash
STREAM_MODE=webrtc ./scripts/shell/launch_with_stream.sh --headless
```

MJPEG fallback:

```bash
STREAM_MODE=mjpeg ./scripts/shell/launch_with_stream.sh --headless
```

## Verify Topic Separation
Agent should validate topic routing before flight:

```bash
gz topic -l | grep camera_link/sensor/camera/image
```

Expected:
- one topic under `/model/holybro_x500...` (drone camera)
- one topic under `/model/fixed_cam...` or `/model/mono_cam_hd...` (monitor camera)

## Flight Test Command
Run mission script separately:

```bash
.venv/bin/python scripts/flight/demo_flight_v2.py
```

`demo_flight_v2.py` is expected to fail fast if drone camera topic is not found.

## Quick Performance Tuning
Use environment variables without code edits:

```bash
STREAM_FPS=20 STREAM_THREADS=2 STREAM_MODE=webrtc ./scripts/shell/launch_with_stream.sh --headless
```

If stutter:
- reduce `STREAM_FPS` to `15`
- keep one browser tab only
- close heavy apps

If sim instability/sensor lag:
- reduce `STREAM_FPS`
- temporarily switch to `STREAM_MODE=mjpeg` for compatibility

## Common Failure Cases

1. Stuck at "Step 3/4: set the camera"
- Cause: fixed camera topic not discovered.
- Check:
  - world contains fixed cam include (`mono_cam_hd`, name `fixed_cam`)
  - `launch.sh` copies `models/mono_cam_hd` into PX4 models
  - `gz topic -l` contains fixed camera topic

2. Stream starts but black video
- Cause: stream connected before frames arrive.
- Check `output/stream_camera.log` for topic used and frame updates.
- Restart launcher once sim is fully up.

3. WebRTC mode fails on clean machine
- Cause: missing deps (`aiortc`, `aiohttp`, `av`).
- Install:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

- Re-run with `STREAM_MODE=webrtc`.
- If still blocked, run `STREAM_MODE=mjpeg` as immediate fallback.

4. Flight detection uses wrong camera
- Must not happen after current fixes.
- Validate camera topic in flight logs contains `/model/holybro_x500`.

## Logs to Collect for Agent Debug
- `output/launch_sim.log`
- `output/stream_camera.log`
- output of:

```bash
git status --short
gz topic -l | grep -E "holybro_x500|fixed_cam|mono_cam_hd|camera_link/sensor/camera/image"
```

## Safe Defaults
- Fixed monitor camera model: `mono_cam_hd`
- Resolution: `1280x720`
- Update rate: `30`
- Default stream mode: `webrtc` (fallback to `mjpeg` if deps missing)

