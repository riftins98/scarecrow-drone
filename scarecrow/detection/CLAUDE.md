# detection

YOLO-based object detection. Currently single-class (pigeon) but the class names come from the model file, so swapping models repurposes the package.

## Files
- `__init__.py` — Package init
- `yolo.py` — `YoloDetector`: callback-driven inference for camera frames. Rate-limited (default 1 inference/sec) to avoid saturating slow sim cameras. `preload_async()` warms up the model in a background thread so MAVSDK connect runs in parallel. Saved image output is configurable so mission scripts can disable routine frame writes, force one trigger image, or throttle pursuit evidence images. Saved detections emit `DETECTION_IMAGE:<path>` to stdout (webapp parses this), and callbacks provide optional saved-image paths plus raw `on_detection_data(detections)` for navigation. The public `confidence` property can be adjusted between search and pursuit phases; no-detection logs include the best below-threshold candidate confidence.
- `tracking.py` — `TargetTracker`: thread-safe adapter for detector callbacks. Stores the highest-confidence latest detection as a generic `TargetObservation` for navigation/pursuit controllers.
