# mono_cam

Mono camera sensor model (1280x720, ~Pi Camera 3 equivalent). Attached to the X500 airframe.

## Files
- `model.sdf` — Camera sensor plugin. Publishes `camera_link/sensor/camera/image` (consumed by `GazeboCamera`). Configures resolution, FOV, and update rate.
- `model.config` — Gazebo model manifest.
