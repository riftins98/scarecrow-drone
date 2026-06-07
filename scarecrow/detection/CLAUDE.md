# detection

YOLO-based object detection for drone camera frames. Mission scripts can restrict accepted classes while still logging the best model candidate for debugging model swaps.

## Files
- `__init__.py` — Package init
- `yolo.py` — `YoloDetector`: callback-driven inference for camera frames. Rate-limited (default 1 inference/sec) to avoid saturating slow sim cameras. `preload_async()` warms up the model in a background thread so MAVSDK connect runs in parallel. Saved image output is configurable so mission scripts can disable routine frame writes, queue specific detection snapshots, or throttle general evidence images. Saved detections emit `DETECTION_IMAGE:<path>` to stdout (webapp parses this), and callbacks provide optional saved-image paths plus raw `on_detection_data(detections)` for navigation. The public `confidence` property can be adjusted between search and pursuit phases; no-detection logs include best-candidate confidence plus class-filter/threshold reasons.
- `tracking.py` — `TargetTracker`: thread-safe adapter for detector callbacks. Stores the highest-confidence latest detection as a generic `TargetObservation` for navigation/pursuit controllers and supports explicit clearing between mission phases to avoid stale handoffs.
