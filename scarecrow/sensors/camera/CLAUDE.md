# camera

Camera interface for sim and (future) hardware. Frames are BGR numpy arrays via a callback API so consumers (e.g. YoloDetector) can subscribe without polling.

## Files
- `__init__.py` — Package init
- `base.py` — `CameraFrame` dataclass (image + timestamp) and `CameraSource` ABC (`start`, `stop`, `get_frame`). Allows context-manager use.
- `gazebo.py` — `GazeboCamera`: polls `gz topic -e` for camera frames from the drone model topic, calls `on_frame(np.ndarray)` for each frame. Records raw PNGs to `output_dir/frames/` and stitches them into an MP4 with ffmpeg after landing. Topic discovery prefers `holybro_x500.../camera/image` and avoids fixed monitoring cameras (`fixed_cam`, `mono_cam_hd`).
