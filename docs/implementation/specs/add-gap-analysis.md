# ADD Gap Analysis

Full comparison between the ADD specification and current implementation.
Reference: `add_scarecrow_drone.pdf` (78 pages)

**Last updated after Phases 0-2 completion.**

## Use Cases Status

| UC | Name | Status | Notes |
|----|------|--------|-------|
| UC1 | Map Area | NOT STARTED | `area_maps` table + CRUD endpoints DONE; mapping flight script + MapUnit integration pending |
| UC2 | Start Detection Flight | DONE | Webapp flow works end-to-end with `demo_flight_v2.py` subprocess |
| UC3 | Record Flight Video | DONE | PNG+ffmpeg pipeline in GazeboCamera; video path tracked via `VIDEO_PATH:` stdout protocol |
| UC4 | Detect Birds | DONE | YoloDetector + camera on_frame callback; detection count via TELEMETRY: protocol |
| UC5 | Chase Birds | NOT STARTED | `chase_events` table + endpoints DONE; ChaseController class pending |
| UC6 | Store Flight Data | DONE | flights + detection_images + telemetry + chase_events tables all exist; repositories working |
| UC7 | Abort Mission | NOT STARTED | `/api/drone/abort` endpoint exists; SIGTERM handler in flight script pending |
| UC8 | View Flight Results | PARTIAL | Flight history + images + video work. Missing: filtering, chase events UI |

## Database Tables

| ADD Table | Status |
|-----------|--------|
| flights | DONE (has area_map_id FK; keeps extra practical cols) |
| detection_images | DONE |
| area_maps | DONE |
| telemetry | DONE |
| chase_events | DONE |

All created via idempotent migrations in `webapp/backend/database/migrations/`.

## Backend Architecture

**ADD requires**: Controllers -> Services -> Repositories -> DTOs -> Database (layered)

**Current**: DONE. 40 API routes across 8 controllers. Services share singletons via `dependencies.py`.

### Missing Backend Components

| Layer | ADD Planned | Exists? |
|-------|-----------|---------|
| DTOs | FlightDTO, AreaMapDTO, TelemetryDTO, ChaseEventDTO, DetectionDTO | DONE (5/5) in `webapp/backend/dtos/` |
| Repositories | Flight, AreaMap, Telemetry, ChaseEvent, DetectionImage | DONE (5/5) in `webapp/backend/repositories/` |
| Services | Flight, Drone, AreaMap, ChaseEvent, Telemetry, Recording, Connection | DONE (8/8) in `webapp/backend/services/` |
| Controllers | Flight, Drone, AreaMap, Detection, ChaseEvent, Connection, Sim, Static | DONE (8/8) in `webapp/backend/controllers/` |

## API Endpoints

DONE: 40 routes across all ADD sections A.1-A.7 plus static file serving.

- A.1 Sim: /api/sim/connect, /api/sim/status (3 routes)
- A.2 Connection: /api/connection/wifi, /ssh, /status, /video/* (6 routes, wifi/ssh mocked for sim)
- A.3 Drone Control: /api/drone/status, /start, /stop, /abort, /return-home, /telemetry (6 routes)
- A.4 Flight History: /api/flights, /{id}, /summary, /telemetry, /images, /recording, DELETE /{id} + legacy /api/flight/start|stop|status (9+3 routes)
- A.5 Area Map: /api/areas CRUD, /{id}/flights, /mapping/start|status (8 routes)
- A.6 Detection: /api/detection/status, /config GET/PUT (3 routes)
- A.7 Chase Event: /api/flights/{id}/chases, /api/chases/{id} (2 routes)

Missing: WebSocket `/api/drone/telemetry/stream` (Phase 7 frontend task).

## OO Classes (Section 5 of ADD)

| ADD Class | Status | Location |
|-----------|--------|----------|
| Drone | DONE | `scarecrow/drone.py` |
| Flight | DONE | `scarecrow/flight/flight.py` (optional -- existing scripts don't use it) |
| DetectionUnit | DONE | YoloDetector in `scarecrow/detection/yolo.py` |
| NavigationUnit | DONE | `scarecrow/navigation/navigation_unit.py` (facade over existing controllers) |
| MapUnit | DONE (stub) | `scarecrow/navigation/map_unit.py` -- bounding-box recorder, not full SLAM |

## Frontend

| ADD UI | Status |
|--------|--------|
| Flight Control Dashboard | PARTIAL -- no abort button, no live telemetry panel |
| Flight History | PARTIAL -- no date/status filtering, no delete button |
| Area Mapping Interface | NOT STARTED |
| Flight Telemetry View | NOT STARTED |
| Detection Image Gallery (separate page) | NOT STARTED -- only modal view exists |
| Chase Event Log | NOT STARTED |

All remaining frontend work lives in Phase 7.

## Testing

**ADD specifies**: 21 unit tests (UT-01..21), 5 integration tests (IT-01..05)

**Current**: 217 tests passing, ~2.5s run time. All UT-01..21 covered plus substantially more.

- 131 unit tests in `tests/unit/` (controllers, repositories, services, OO classes)
- 62 integration tests in `tests/integration/` (all 40 API routes + end-to-end flow)
- Missing: IT-03, IT-04, IT-05 blocked on Phase 3-6 (need mapping/chase flight scripts to integrate with)

## scarecrow Package Components

All preserved from the original working code; wrapped where needed:

- `scarecrow/drone.py` -- Drone class (NEW in Phase 2; 62% coverage because async MAVSDK streams require sim to test)
- `scarecrow/controllers/wall_follow.py` -- WallFollowController (PD, SVD yaw)
- `scarecrow/controllers/distance_stabilizer.py` -- DistanceStabilizerController (multi-axis)
- `scarecrow/controllers/front_wall_detector.py` -- FrontWallDetector (clustering, temporal)
- `scarecrow/controllers/rotation.py` -- rotate_90 (compass + lidar SVD)
- `scarecrow/detection/yolo.py` -- YoloDetector + preload_async
- `scarecrow/flight/helpers.py` -- get_position, wait_for_altitude, wait_for_stable
- `scarecrow/flight/stabilization.py` -- lidar_stabilize (async offboard wrapper)
- `scarecrow/flight/flight.py` -- Flight orchestrator (NEW)
- `scarecrow/navigation/navigation_unit.py` -- NavigationUnit facade (NEW)
- `scarecrow/navigation/map_unit.py` -- MapUnit area recorder (NEW)
- `scarecrow/sensors/gz_utils.py` -- get_gz_env + prefetch_gz_env_async (NEW helper)
- `scarecrow/sensors/lidar/base.py` -- LidarScan (360 range data)
- `scarecrow/sensors/lidar/gazebo.py` -- GazeboLidar (fixed topic filter in Phase 2)
- `scarecrow/sensors/lidar/rplidar.py` -- RPLidar (USB serial, resampling)
- `scarecrow/sensors/camera/base.py` -- CameraSource ABC
- `scarecrow/sensors/camera/gazebo.py` -- GazeboCamera (gz topic, PNG parsing, ffmpeg)

## Flight scripts

- `scripts/flight/demo_flight.py` -- v1, kept as fallback
- `scripts/flight/demo_flight_v2.py` -- uses OO layer, spawned by webapp via DetectionService
- `scripts/flight/room_circuit.py`, `wall_follow.py`, `detect_pigeons.py`, `sensor_check.py` -- unchanged
