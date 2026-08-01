# scripts

Flight control scripts and shell launch utilities. Flight scripts run as standalone processes (spawned by the webapp as subprocesses) and communicate results via stdout protocol lines (DETECTION_IMAGE:, TELEMETRY:, etc.).

## Subdirectories
- `flight/` — Python autonomous flight mission scripts using MAVSDK + scarecrow package (see `flight/CLAUDE.md`)
- `shell/` — Bash scripts for PX4+Gazebo simulation launch and environment setup (see `shell/CLAUDE.md`)

## Files
- `stream_camera.py` — MJPEG monitor server. **The default on every platform** (`STREAM_MODE=mjpeg`): the container has no choice, since WebRTC's ICE media path cannot cross Docker port mapping, and running a different transport on macOS meant the two delivery tracks shipped different code for the same feature. Measured at 1280x720: JPEG q92 costs **1.69ms/frame and 73KiB**, against **8.34ms and ~100KiB** for aiortc's software H.264 at 8Mbps — cheaper *and* sharper, because the stream never leaves the machine and H.264's inter-frame compression solves a bandwidth problem that does not exist here. Default quality raised 68 -> 92 for the same reason. `CameraGate` runs the cameras only while a client is attached (an unsubscribed gz-sensors camera is not rendered at all), with a grace period so a browser refresh does not re-run topic discovery; the JPEG encoder also idles when nobody is watching.
- `stream_camera_webrtc.py` — WebRTC monitor server, still supported via `STREAM_MODE=webrtc` but no longer the default. Carries the same `CameraGate`. `raise_encoder_bitrate()` lifts aiortc's ceiling (1Mbps default / 3Mbps max, sized for the open internet) to `--bitrate`, default 8Mbps — at 720p the stock limit visibly softens the picture, and the ceiling protects nothing on loopback. Cannot be used in Docker.
- `test_cam.py` — Debug helper to pull a single Gazebo camera frame and save it to `output/test_capture.png`.
