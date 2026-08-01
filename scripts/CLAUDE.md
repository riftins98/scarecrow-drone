# scripts

Flight control scripts and shell launch utilities. Flight scripts run as standalone processes (spawned by the webapp as subprocesses) and communicate results via stdout protocol lines (DETECTION_IMAGE:, TELEMETRY:, etc.).

## Subdirectories
- `flight/` — Python autonomous flight mission scripts using MAVSDK + scarecrow package (see `flight/CLAUDE.md`)
- `shell/` — Bash scripts for PX4+Gazebo simulation launch and environment setup (see `shell/CLAUDE.md`)

## Files
- `stream_camera.py` — MJPEG monitor server, and **the only streamer on every platform**. A WebRTC streamer existed alongside it and was deleted: it could not run in Docker at all (ICE negotiates media over dynamic UDP ports, and only the published TCP port crosses Docker's port mapping — signalling connected, video stayed black), so it was a macOS-only path, and a second transport meant the two delivery tracks could drift apart on the same feature. It was also the slower one. Measured at 1280x720: JPEG q92 costs **1.69ms/frame and 73KiB**, against **8.34ms and ~100KiB** for aiortc's software H.264 at 8Mbps — cheaper *and* sharper, because the stream never leaves the machine and H.264's inter-frame compression solves a bandwidth problem that does not exist here. Default quality is 92, raised from 68 for the same reason. `CameraGate` runs the cameras only while a client is attached (an unsubscribed gz-sensors camera is not rendered at all), with a grace period so a browser refresh does not re-run topic discovery; the JPEG encoder also idles when nobody is watching.
