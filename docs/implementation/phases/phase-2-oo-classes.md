# Phase 2: Domain OO Classes

**Status**: COMPLETE -- merged to main
**Dependencies**: Phase 1 (layered backend)
**Actual size**: Large (4 new classes + 4 supporting generalizations + 1 refactored flight script + 46 tests)

## Goal

Create the ADD's domain classes (Drone, Flight, NavigationUnit, MapUnit) that replace scattered MAVSDK calls, PLUS the supporting helpers needed to actually USE them in real flight scripts. The existing flight scripts stay untouched so nothing breaks; a new `demo_flight_v2.py` uses the OO layer.

## What shipped

### Core OO Classes

| Class | File | Purpose |
|-------|------|---------|
| `Drone` | `scarecrow/drone.py` | MAVSDK wrapper: connect, arm/disarm, takeoff, offboard, telemetry, set_velocity. Uses `VelocityCommand` dataclass from `controllers.wall_follow`. |
| `NavigationUnit` | `scarecrow/navigation/navigation_unit.py` | Facade over existing controllers: `wall_follow()`, `stabilize()`, `rotate()`, `circuit()`. Delegates to `WallFollowController`, `FrontWallDetector`, `rotate_90()`, `lidar_stabilize()`. |
| `Flight` | `scarecrow/flight/flight.py` | Mission orchestrator with lifecycle callbacks: `run(mission_func, altitude)`. Optional -- existing scripts don't use it. |
| `MapUnit` | `scarecrow/navigation/map_unit.py` | Area boundary recording for UC1. Records lidar-derived wall distances at sample points, computes bounding box envelope. Stub -- not full SLAM. |

### Supporting Generalizations (discovered during v2 rewrite)

These turned out to be required for `demo_flight_v2.py` to compose cleanly:

| What | Where | Purpose |
|------|-------|---------|
| `Drone.verify_gps_denied_params()` | `scarecrow/drone.py` | Reads PX4 params (EKF2_GPS_CTRL, EKF2_OF_CTRL, SYS_HAS_GPS) and confirms GPS-denied configuration. Returns bool. |
| `Drone.prepare_takeoff()` | `scarecrow/drone.py` | Pre-arm setup: records ground_z, calls set_takeoff_altitude, settle delay. Must be called BEFORE arm -- PX4 validates these during preflight. |
| `Drone.set_ekf_origin()` | `scarecrow/drone.py` | Calls MAVSDK `set_gps_global_origin(0,0,0)`. Returns bool. On failure, prints fallback instruction to set via `commander set_ekf_origin 0 0 0` in pxh>. |
| `prefetch_gz_env_async()` + `GzPrefetchResult` | `scarecrow/sensors/gz_utils.py` | Fetches gz env + topic list in a background thread. Overlaps ~2s of setup with MAVSDK handshake. |
| `YoloDetector.preload_async()` | `scarecrow/detection/yolo.py` | Starts `load_model()` in a daemon thread. Overlaps ML warmup with MAVSDK connect. |
| `GazeboLidar._discover_topic(topic_list=...)` | `scarecrow/sensors/lidar/gazebo.py` | Now accepts cached topic list (avoids re-running `gz topic -l`). Filters `/points` variant correctly. |

### Robustness additions (from real sim validation)

| What | Why |
|------|-----|
| `Drone.arm()` retries 2x on COMMAND_DENIED with 1s delay | PX4 sometimes rejects the first arm while preflight finalizes |
| `Drone.arm()` detects "already armed" state and force-kills first | Previous failed flight could leave drone armed; new arm would otherwise deadlock |
| `Drone.disarm()` falls back to `action.kill()` on disarm failure | Guarantees motors off even when disarm is rejected |
| `Drone._is_currently_armed()` | Reads telemetry.armed() stream with 2s timeout |

### Refactored flight script

**File**: `scripts/flight/demo_flight_v2.py`

Uses the OO layer end-to-end. ~180 lines vs v1's ~520.

Sequence:
1. Parse `--flight-id` (required; webapp owns DB)
2. Parallel warmup: `detector.preload_async()` + `prefetch_gz_env_async()`
3. `drone.connect()` / `wait_for_health()`
4. `drone.verify_gps_denied_params()` (abort if mismatch)
5. `drone.set_ekf_origin()`
6. Start `GazeboLidar` + `GazeboCamera` with cached topics
7. `drone.prepare_takeoff(TARGET_ALT)` -- BEFORE arm
8. `drone.arm()`
9. `drone.takeoff(TARGET_ALT)`
10. `drone.start_offboard()`
11. `nav.stabilize()` pre-hover
12. Hover loop with YOLO + DistanceStabilizer + periodic TELEMETRY emission
13. `lidar_stabilize()` pre-land
14. Lidar-locked descent to LAND_AGL
15. `drone.stop_offboard()` -> `drone.land()` -> wait for touchdown -> `drone.disarm()` (with kill fallback)
16. Build video via `camera.save_video()`, emit `VIDEO_PATH:`

### Stdout protocol (webapp integration)

The script emits these lines for `DetectionService._monitor()` to parse:

| Line | Triggers |
|------|----------|
| `DETECTION_IMAGE:/path/to/img.png` | Bird detected; saved image path |
| `TELEMETRY:{"battery":100.0,"distance":0.35,"detections":5}` | Every ~1s during hover |
| `VIDEO_PATH:/path/to/flight_camera.mp4` | After landing, once video is built |

Does NOT touch the DB directly -- the webapp owns all DB writes via repositories.

### Webapp integration changes

In this phase we also fixed the webapp side to match the new protocol:

- `webapp/backend/services/detection_service.py`:
  - Parses `TELEMETRY:` -> updates `pigeons_detected`
  - Parses `VIDEO_PATH:` -> stores on service
  - Added `self.video_path` and `self.latest_telemetry`
  - Reset state in `start()` so subsequent flights don't inherit old values
- `webapp/backend/controllers/flight_controller.py`:
  - `/api/flight/status` patches `video_path` onto finalized flights if the subprocess builds the video AFTER the user clicks stop
- `webapp/backend/services/detection_service.py:35`:
  - Flight script path changed from `demo_flight.py` to `demo_flight_v2.py`

## Tests

46 unit tests added across:
- `tests/unit/scarecrow/drone/test_drone.py` -- 15 tests including verify_gps_denied_params
- `tests/unit/scarecrow/navigation/test_navigation_unit.py` -- 6 tests
- `tests/unit/scarecrow/navigation/test_map_unit.py` -- 10 tests
- `tests/unit/scarecrow/flight/test_flight.py` -- 9 tests
- `tests/unit/scarecrow/detection/test_yolo_detector.py` -- 6 tests (added preload_async)
- `tests/unit/scarecrow/sensors/test_gz_utils.py` -- 3 tests (new file)
- `tests/unit/scarecrow/sensors/test_gazebo_lidar.py` -- 4 tests (new file)

Total project tests: 217 passing, 2.6s.

## Design Decisions

### Flight class is OPTIONAL

`demo_flight.py` (v1) and `room_circuit.py` do NOT use `Flight`. They keep their proven procedural structure. `Flight` is for NEW missions that want a clean lifecycle scaffold. Forcing the refactor would risk breaking working drone code for zero benefit.

### `demo_flight_v2.py` is a new file, not a replacement

Kept v1 as fallback during validation. The webapp now spawns v2. If v2 ever breaks, a one-line change in `detection_service.py` reverts to v1.

### NavigationUnit delegates, not reimplements

`NavigationUnit.rotate()` just calls the existing `rotate_90()` helper. `stabilize()` calls `lidar_stabilize()`. Only `wall_follow()` contains its own async loop (because the original `wall_follow()` helper was tightly coupled to the `demo_flight`-style procedural script). No controller was rewritten.

### Circular import avoidance

`scarecrow.drone` imports `scarecrow.flight.helpers`, and `scarecrow.flight.flight` imports `scarecrow.drone`. To avoid a cycle, `scarecrow.flight.__init__.py` does NOT re-export `Flight`. Import it directly: `from scarecrow.flight.flight import Flight`.

### MapUnit is a stub

Records positions + wall distances. Finishes with axis-aligned bounding box. Good enough to demonstrate the concept for UC1. Full SLAM is out of scope for the university project.

## Verification (actual manual sim tests performed)

1. `pytest tests/` -- 217 passed, 2.6s
2. Standalone: `python3 scripts/flight/demo_flight_v2.py --flight-id test-v2` -- takeoff, 5 detections (80-88% confidence), lidar-locked hover, descent, disarm, video built (569 frames, 956KB mp4)
3. Webapp: click "Start Detection Flight" -> drone flies in Gazebo -> history shows completed flight with pigeons count + detection images + playable video

## Known post-validation issues resolved

| Issue | Root cause | Fix |
|-------|-----------|-----|
| Arm COMMAND_DENIED on second flight | Previous flight didn't disarm cleanly; drone still armed | Added `arm()` pre-check + force-kill |
| "Pigeons Detected = 0" despite images | `DetectionService` didn't parse `TELEMETRY:` lines | Added JSON parsing |
| "No recording available" despite video on disk | `DetectionService` didn't parse `VIDEO_PATH:` + stop() wrote DB before video built | Parse VIDEO_PATH + patch video_path during status polling |
| Landing with rotors still spinning | `disarm()` silently failed; no kill fallback | `disarm(force_kill_on_failure=True)` default |
| Wrong PX4 pxh> command in docs | `set_gps_global_origin` is MAVSDK, not PX4 subcommand | Corrected to `set_ekf_origin` everywhere |
