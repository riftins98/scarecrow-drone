# Phase 4: UC4 + UC3 — Detection Flight with Video Recording

**Dependencies**: Phase 2 (Drone class), Phase 3 (area maps exist for patrol route)
**Estimated size**: Medium
**Simulation required**: Yes (PX4 + Gazebo with drone_garage world + pigeon_billboard)

## Context (from ADD)

**UC4 — Detect Birds** and **UC3 — Record Flight Video** work together during a detection flight. The operator starts a detection flight from the webapp. The drone patrols a mapped area while simultaneously recording video and running YOLO detection on camera frames. When a bird is detected, the annotated image is saved and a detection record is created in the database.

### ADD Sequence: UC2 Start Detection Flight (Section 4.1.2)
```
Operator -> Dashboard: Click "Start Detection Flight"
Dashboard -> FlightController: POST /api/drone/start {areaMapId}
FlightController -> FlightService: create_flight()
FlightService -> Flight: start()
Flight -> DB: INSERT flights + INSERT telemetry
FlightService -> [Spawn flight subprocess with area_map_id]
Dashboard: polls /api/drone/status for real-time updates
```

### ADD Sequence: UC3 Record Video (Section 4.1.3)
```
FlightService -> VideoRecorder: start_recording()
VideoRecorder -> FFmpegProcess: initialize_ffmpeg()
FFmpegProcess: ready
VideoRecorder -> FFmpegProcess: capture_frame() [loop]
FFmpegProcess -> FileSystem: write_file()
VideoRecorder -> DB: save_video_path()
```

### ADD Sequence: UC4 Detect Birds (Section 4.1.4)
```
VideoRecorder -> DetectionService: send_frame()
DetectionService -> YOLOModel: preprocess_frame() -> detect()
YOLOModel -> DetectionService: detections
DetectionService -> DetectionImage: draw_bboxes()
DetectionImage -> FileSystem: write_image()
DetectionImage -> DB: INSERT detection_images
DB -> Telemetry: UPDATE detections count
```

### ADD Detection State Machine (Section 4.3.3)
```
Initial -> Idle (flight started)
Idle -> Scanning (camera feed available)
Scanning -> Processing Frame (frame received)
Processing Frame -> Bird Detected (birds found) -> Saving Detection -> Scanning
Processing Frame -> Scanning (no birds)
Scanning/Processing -> Idle (camera feed lost / flight stopped)
```

---

## Existing Code (what works today)

| Component | File | Status |
|-----------|------|--------|
| YoloDetector | `scarecrow/detection/yolo.py` | **Working**. Rate-limited, thread-safe, callbacks, saves annotated images |
| GazeboCamera | `scarecrow/sensors/camera/gazebo.py` | **Working**. Polls gz topic, on_frame callback, PNG recording, ffmpeg video |
| DetectionService | `webapp/backend/services/detection_service.py` | **Working**. Spawns demo_flight.py, parses DETECTION_IMAGE: from stdout |
| demo_flight.py | `scripts/flight/demo_flight.py` | **Working**. Connects, arms, takes off, hovers, runs YOLO, lands |
| Flight DB functions | `webapp/backend/database/db.py` | **Working**. create_flight, end_flight, add_detection_image |
| YOLO model | `models/yolo/best_v4.pt` | **Working**. Trained YOLOv8 pigeon model |
| Pigeon billboard | `models/pigeon_billboard/` | **Working**. Gazebo visual target for testing detection |

**Key insight**: UC4 detection is already working end-to-end. This phase is about:
1. Enhancing it to use area maps for patrol routes (instead of static hover)
2. Properly integrating video recording (UC3) into the webapp
3. Adding telemetry tracking during flight
4. Connecting to the new layered backend from Phase 1

---

## What Needs to Change

### 1. Enhance demo_flight.py to support patrol mode

Currently `demo_flight.py` hovers in place and runs YOLO. The ADD describes a **patrol flight** that follows a mapped area while detecting.

**File**: `scripts/flight/demo_flight.py` (modify) or create `scripts/flight/patrol_flight.py` (new)

**Enhanced flight sequence**:
```
1. Parse args: --flight-id <id>, --area-map-id <id> (optional)
2. Connect, verify sensors, arm, takeoff (KEEP existing code exactly)
3. Start lidar + camera + YOLO detector (KEEP existing code exactly)
4. Start camera recording: camera.start_recording(output_dir)
5. Connect YoloDetector to camera: camera.on_frame = detector.process_frame
6. If area_map_id provided:
   a. Load area map boundaries from DB (or receive as JSON arg)
   b. Use NavigationUnit.wall_follow() to patrol along walls
   c. At each corner: NavigationUnit.rotate(), stabilize, continue
   d. While patrolling: YOLO runs continuously via on_frame callback
7. If no area_map_id (legacy mode):
   a. Stabilize at hover position (KEEP existing code)
   b. Hover for HOVER_DURATION while YOLO runs
8. Stop camera recording: camera.stop_recording()
9. Land
10. Build video: camera.save_video() (AFTER landing — critical constraint)
11. Print summary: detection count, frames processed, video path
```

**Stdout protocol** (extend existing):
- `DETECTION_IMAGE:/path/to/img.png` — (existing, keep as-is)
- `TELEMETRY:{"battery":85.0,"distance":12.5,"detections":3}` — new, for telemetry tracking
- `VIDEO_PATH:/path/to/flight_camera.mp4` — new, after video is built
- `FLIGHT_SUMMARY:{"pigeons":5,"frames":120}` — (existing pattern, formalize)

### 2. Add telemetry output to flight script

During flight, periodically output telemetry for the webapp to track:

```python
# In the flight loop, every 5 seconds:
async def report_telemetry(drone, detector, start_pos):
    """Print telemetry line for webapp parsing."""
    pos = await get_position(drone)
    battery = 100.0  # In sim, battery is simulated
    distance = compute_distance(start_pos, pos)  # NED distance from start
    print(f"TELEMETRY:{json.dumps({
        'battery': round(battery, 1),
        'distance': round(distance, 2),
        'detections': detector.detections_total,
    })}", flush=True)
```

### 3. DroneService telemetry parsing

**File**: `webapp/backend/services/drone_service.py` (extend from Phase 1)

Add TELEMETRY: and VIDEO_PATH: parsing to the subprocess monitor (same pattern as DetectionService._monitor()):

```python
def _monitor(self):
    for line in self._process.stdout:
        line = line.strip()
        if line.startswith("TELEMETRY:"):
            data = json.loads(line.split("TELEMETRY:", 1)[1])
            self._latest_telemetry = data
            # Update telemetry DB record
            self.telemetry_service.update_telemetry(
                self._flight_id, **data
            )
        elif line.startswith("VIDEO_PATH:"):
            self._video_path = line.split("VIDEO_PATH:", 1)[1]
        elif "DETECTION_IMAGE:" in line:
            # ... existing detection parsing ...
```

### 4. RecordingService integration

**File**: `webapp/backend/services/recording_service.py` (from Phase 1)

The recording happens inside the flight subprocess (GazeboCamera.start_recording/stop_recording/save_video). The RecordingService on the webapp side just tracks status:

```python
class RecordingService:
    def __init__(self):
        self.recording = False
        self.video_path: Optional[str] = None

    def on_flight_started(self, flight_id: str):
        self.recording = True
        self.video_path = None

    def on_video_ready(self, path: str):
        self.recording = False
        self.video_path = path

    def get_status(self) -> dict:
        return {"recording": self.recording, "videoPath": self.video_path}
```

### 5. Wire FlightService to use area maps

**File**: `webapp/backend/services/flight_service.py` (extend from Phase 1)

When starting a flight with an area_map_id, pass it to the subprocess:

```python
def start_flight(self, area_map_id: Optional[int] = None) -> FlightDTO:
    flight = self.flight_repo.create(area_map_id=area_map_id)
    self.telemetry_repo.create(TelemetryCreateDTO(flight_id=flight.id))

    # Build subprocess args
    args = ["python3", FLIGHT_SCRIPT, "--flight-id", flight.id]
    if area_map_id:
        args.extend(["--area-map-id", str(area_map_id)])

    # Spawn via DroneService
    self.drone_service.start_subprocess(args)
    return flight
```

---

## Simulation Setup

**World**: `drone_garage.sdf` (has pigeon_billboard for detection testing)

**Launch**:
```bash
source scripts/shell/env.sh
./scripts/shell/launch.sh drone_garage
```

**In pxh> console**:
```
commander set_gps_global_origin 0 0 0
```

**Important constraints** (from memory):
- Camera frame parsing MUST happen after flight, not during (crashes destabilize drone)
- GazeboCamera already handles this: records raw .bin during flight, parses to PNG after landing
- Optical flow needs 2.5m+ altitude for good feature tracking
- Never param set EKF2 at runtime

---

## Verification

### Test detection (already working, verify no regression)
```bash
source .venv-mavsdk/bin/activate
python3 scripts/flight/demo_flight.py

# Expected: drone takes off, hovers, YOLO runs, detects pigeon billboard,
# saves annotated images, lands, builds video
# Check: webapp/output/<flight_id>/detections/ has detection PNGs
# Check: webapp/output/<flight_id>/flight_camera.mp4 exists
```

### Test telemetry output (new)
```bash
# Run flight, grep for TELEMETRY lines
python3 scripts/flight/demo_flight.py 2>&1 | grep TELEMETRY

# Expected: TELEMETRY:{"battery":100.0,"distance":0.5,"detections":2}
```

### Test via webapp
```bash
cd webapp && ./start.sh
# 1. Connect sim
# 2. Start detection flight (optionally select area map)
# 3. Watch real-time: pigeons detected count, frames processed
# 4. Stop flight
# 5. Check flight history: detection images visible, video path set
# 6. Check DB: telemetry record exists for flight
```

### Test video recording specifically
```bash
# After flight completes:
ls webapp/output/<flight_id>/
# Should see: flight_camera.mp4, camera_ground.png, camera_flight.png, detections/

# Verify video plays:
open webapp/output/<flight_id>/flight_camera.mp4
```
