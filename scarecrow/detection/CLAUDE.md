# detection

YOLO-based object detection. Currently single-class (pigeon) but the class names come from the model file, so swapping models repurposes the package.

## Files
- `__init__.py` — Package init
- `yolo.py` — `YoloDetector`: callback-driven inference for camera frames. Rate-limited (default 1 inference/sec) to avoid saturating slow sim cameras. `preload_async()` warms up the model in a background thread so MAVSDK connect runs in parallel. Each detection saves an annotated frame to `output_dir/detections/`, emits `DETECTION_IMAGE:<path>` to stdout (webapp parses this), and calls optional `on_detection(img_path)` / `on_detection_data(detections)` callbacks. The public `confidence` property can be adjusted between search and pursuit phases; no-detection logs include the best below-threshold candidate confidence.
- `tracking.py` — `TargetTracker`: thread-safe adapter for detector callbacks. Stores the highest-confidence latest detection as a generic `TargetObservation` for navigation/pursuit controllers.
