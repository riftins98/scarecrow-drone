# ADD Gap Analysis

Full comparison between the ADD specification and current implementation.
Reference: `add_scarecrow_drone.pdf` (78 pages)

## Use Cases Status

| UC | Name | Status | Gap |
|----|------|--------|-----|
| UC1 | Map Area | NOT STARTED | No area_maps table, no mapping UI, no /api/areas endpoints |
| UC2 | Start Detection Flight | PARTIAL | Works from dashboard, but no area map prerequisite |
| UC3 | Record Flight Video | PARTIAL | video_path in DB, GStreamer broken, PNG+ffmpeg workaround planned |
| UC4 | Detect Birds | DONE | YoloDetector works, saves annotated frames, stores in DB |
| UC5 | Chase Birds | NOT STARTED | No chase logic, no chase_events table, no counter-measures |
| UC6 | Store Flight Data | PARTIAL | flights + detection_images stored. Missing: telemetry, chase_events, area_map link |
| UC7 | Abort Mission | NOT STARTED | No abort endpoint, no return-to-home from webapp |
| UC8 | View Flight Results | PARTIAL | Flight history + images. Missing: chase events, telemetry, video, filtering |

## Database Tables

| ADD Table | Exists? | Gap |
|-----------|---------|-----|
| flights | PARTIAL | Missing area_map_id FK. Has extra cols (pigeons_detected, frames_processed, duration). Uses TEXT id |
| detection_images | YES | Matches ADD |
| area_maps | NO | Entire table missing |
| telemetry | NO | Entire table missing (battery_level, distance, detections) |
| chase_events | NO | Entire table missing |

## Backend Architecture

**ADD requires**: Controllers -> Services -> Repositories -> DTOs -> Database (layered)

**Current**: flat app.py (all routes) + db.py (plain functions) + 2 services

### Missing Backend Components

| Layer | ADD Planned | Exists? |
|-------|-----------|---------|
| DTOs | FlightDTO, AreaMapDTO, TelemetryDTO, ChaseEventDTO, DetectionDTO | NO (0/5) |
| Repositories | Flight, AreaMap, Telemetry, ChaseEvent, DetectionImage, Drone | NO (0/6) |
| Services | Flight, Drone, AreaMap, ChaseEvent, Telemetry, Recording, Connection | PARTIAL (2/9: SimService, DetectionService) |
| Controllers | Flight, Drone, AreaMap, Detection, ChaseEvent, Connection, Telemetry | NO (0/7, everything in app.py) |

## API Endpoints

### Implemented (A.1 current sim endpoints)
- POST/DELETE /api/sim/connect, GET /api/sim/status
- POST /api/flight/start, POST /api/flight/stop, GET /api/flight/status
- GET /api/flights, GET /api/flights/{id}, GET /api/flights/{id}/images, GET /api/flights/{id}/recording
- GET /api/health

### NOT Implemented (A.2-A.7 target endpoints)
- A.2 Connection: /api/connection/wifi, /api/connection/ssh, /api/connection/video/*, /api/connection/status
- A.3 Drone Control: /api/drone/status, start, stop, abort, return-home, telemetry, WS telemetry/stream
- A.4 Flight History: /api/flights/{id}/summary, /api/flights/{id}/telemetry, DELETE /api/flights/{id}
- A.5 Area Map: /api/areas (full CRUD), /api/areas/{id}/flights, /api/areas/mapping/start|status
- A.6 Detection: /api/detection/status, /api/detection/config
- A.7 Chase Event: /api/flights/{id}/chases, /api/chases/{id}

## OO Classes (Section 5 of ADD)

| ADD Class | Current | Gap |
|-----------|---------|-----|
| Drone (takeoff, land, return_home, emergency_stop, telemetry) | Scattered across flight scripts | No wrapper class |
| Flight (orchestrator coordinating all units) | Procedural in scripts | No orchestrator class |
| DetectionUnit | YoloDetector in scarecrow/detection/yolo.py | GOOD MATCH |
| NavigationUnit (patrol, chase trajectory, waypoints) | scarecrow/controllers/ (WallFollow, DistanceStabilizer, FrontWallDetector, rotate_90) | Algorithms exist, no unified class |
| MapUnit (create/validate/manage area maps) | None | NOT STARTED |

## Frontend

| ADD UI | Exists? | Gap |
|--------|---------|-----|
| Flight Control Dashboard | PARTIAL | No abort button, no live feed, no telemetry |
| Flight History | PARTIAL | No date/status filtering, no search, no delete |
| Area Mapping Interface | NO | Not implemented |
| Flight Telemetry View | NO | Not implemented |
| Detection Image Gallery | PARTIAL | In modal only, no separate page |
| Chase Event Log | NO | Not implemented |

## Testing

**ADD specifies**: 21 unit tests (UT-01 through UT-21), 5 integration tests (IT-01 through IT-05)
**Current**: ZERO tests. No tests/ directory.

## scarecrow Package (what DOES exist and is solid)

These components are well-implemented and tested manually:
- `scarecrow/controllers/wall_follow.py` -- WallFollowController (PD, SVD yaw)
- `scarecrow/controllers/distance_stabilizer.py` -- DistanceStabilizerController (multi-axis)
- `scarecrow/controllers/front_wall_detector.py` -- FrontWallDetector (clustering, temporal)
- `scarecrow/controllers/rotation.py` -- rotate_90 (compass + lidar SVD)
- `scarecrow/sensors/lidar/base.py` -- LidarScan (360 range data, geometry methods)
- `scarecrow/sensors/lidar/gazebo.py` -- GazeboLidar (gz topic CLI, background thread)
- `scarecrow/sensors/lidar/rplidar.py` -- RPLidar (USB serial, resampling)
- `scarecrow/sensors/camera/base.py` -- CameraSource ABC
- `scarecrow/sensors/camera/gazebo.py` -- GazeboCamera (gz topic, PNG parsing, ffmpeg)
- `scarecrow/detection/yolo.py` -- YoloDetector (rate-limited, thread-safe, callbacks)
- `scarecrow/flight/helpers.py` -- get_position, wait_for_altitude, wait_for_stable
- `scarecrow/flight/stabilization.py` -- lidar_stabilize (async offboard wrapper)
