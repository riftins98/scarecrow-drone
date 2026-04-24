# config

Gazebo server configuration loaded when the simulator starts.

## Files
- `server.config` — Registers Gazebo world plugins: physics, user-commands, scene-broadcaster, contact, IMU, air-pressure, air-speed, apply-link-wrench, navsat, magnetometer, sensors (ogre2 render engine), and the custom `libOpticalFlowSystem` plugin. The `libGstCameraSystem` plugin is intentionally commented out — GStreamer is broken on the dev Mac; the codebase uses the PNG+ffmpeg fallback in `scarecrow/sensors/camera/gazebo.py` instead.
