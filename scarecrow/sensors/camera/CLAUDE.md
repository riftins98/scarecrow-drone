# camera

Camera interface for sim and (future) hardware. Frames are BGR numpy arrays via a callback API so consumers (e.g. YoloDetector) can subscribe without polling.

## Files
- `__init__.py` — Package init
- `base.py` — `CameraFrame` dataclass (image + timestamp) and `CameraSource` ABC (`start`, `stop`, `get_frame`). Allows context-manager use.
- `gazebo.py` — `GazeboCamera`: reads camera frames from the drone model topic and calls `on_frame(np.ndarray)` for each. Prefers an in-process `gz.transport13` subscription (`frame_from_proto`); falls back to `gz topic -e -n 1` polling (`parse_gz_frame`, which unescapes protobuf *text*). Both converge on `_publish()`, so the `on_frame` contract — the only thing YOLO and the WebRTC streamer consume — is identical either way. Recording writes decoded PNGs; `save_video()` still reads legacy `raw_*.bin` dirs. **Recording is currently unwired**: the mission prints "Camera recording: disabled" and `RecordingService` holds no camera, so that path is unit-tested but never exercised in a live run. Topic discovery prefers `holybro_x500.../camera/image` and avoids fixed monitoring cameras (`fixed_cam`, `mono_cam_hd`).
