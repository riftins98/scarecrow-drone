# scripts

Flight control scripts and shell launch utilities. Flight scripts run as standalone processes (spawned by the webapp as subprocesses) and communicate results via stdout protocol lines (DETECTION_IMAGE:, TELEMETRY:, etc.).

## Subdirectories
- `flight/` — Python autonomous flight mission scripts using MAVSDK + scarecrow package (see `flight/CLAUDE.md`)
- `shell/` — Bash scripts for PX4+Gazebo simulation launch and environment setup (see `shell/CLAUDE.md`)

## Files
- `stream_camera.py` — MJPEG fixed-camera monitor server (fallback mode). Serves full-page browser viewer and streams latest fixed camera frame.
- `stream_camera_webrtc.py` — WebRTC monitor server (preferred mode) for smoother H.264-capable browser playback in headless runs.
