# detection

YOLOv8 object detection for drone camera frames. Callback-driven, rate-limited, runs inference in a background thread.

## Files
- `__init__.py` — Package init (empty).
- `yolo.py` — `YoloDetector`: wraps an Ultralytics YOLO model. Designed to be plugged into `CameraSource.on_frame`. Rate-limits inference to at most one call per `min_interval` seconds, saves annotated frames to `output_dir`, and fires `on_detection(img_path)` callback when pigeons are seen. `preload_async()` loads weights in a background thread so model init overlaps MAVSDK connect.
