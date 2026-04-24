# camera

Camera abstraction with sim and (future) hardware drivers. All consumers work with `CameraFrame` objects regardless of source.

## Files
- `__init__.py` — Package init (empty).
- `base.py` — `CameraFrame` dataclass (BGR numpy image + timestamp + height/width properties). `CameraSource` ABC with `start()`, `stop()`, `get_frame()`, and `on_frame` callback hook.
- `gazebo.py` — `GazeboCamera`: reads frames from Gazebo via `gz topic -e -n 1` subprocess polling. `parse_gz_frame()` parses the protobuf text format with embedded image bytes. Supports recording raw PNGs to disk and stitching them into an MP4 with ffmpeg after flight (GStreamer path disabled — broken on Mac).
