# Phase 1: Backend Architecture Refactor

**Dependencies**: Phase 0 (database migrations)
**Estimated size**: Large (20+ files)

## Goal

Restructure the flat `app.py` + `db.py` into the ADD's layered architecture:
Controllers -> Services -> Repositories -> DTOs -> Database

## Pre-read

Before starting, read these files:
- `webapp/backend/app.py` -- current monolith with all routes
- `webapp/backend/database/db.py` -- current plain functions
- `webapp/backend/services/sim_service.py` -- existing service pattern
- `webapp/backend/services/detection_service.py` -- existing service pattern
- `docs/implementation/specs/code-style.md` -- naming, imports, type hints
- `docs/implementation/specs/security.md` -- parameterized queries, error responses

## Phase 1a: DTOs (Pydantic Models)

Create `webapp/backend/dtos/` package:

### `webapp/backend/dtos/__init__.py`
Export all DTOs.

### `webapp/backend/dtos/flight_dto.py`
```python
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class FlightCreateDTO(BaseModel):
    area_map_id: Optional[int] = None

class FlightDTO(BaseModel):
    id: str
    area_map_id: Optional[int] = None
    start_time: str
    end_time: Optional[str] = None
    duration: float = 0
    pigeons_detected: int = 0
    frames_processed: int = 0
    status: str = "in_progress"
    video_path: Optional[str] = None

class FlightSummaryDTO(BaseModel):
    flight_id: str
    duration: float
    total_detections: int
    avg_speed: Optional[float] = None
```

### `webapp/backend/dtos/area_map_dto.py`
```python
from pydantic import BaseModel
from typing import Optional

class AreaMapCreateDTO(BaseModel):
    name: str
    boundaries: Optional[str] = None  # JSON string
    home_point: Optional[str] = None  # JSON coordinate

class AreaMapDTO(BaseModel):
    id: int
    name: str
    created_at: str
    updated_at: str
    boundaries: Optional[str] = None
    area_size: Optional[float] = None
    status: str = "draft"
```

### `webapp/backend/dtos/telemetry_dto.py`
```python
from pydantic import BaseModel
from typing import Optional

class TelemetryCreateDTO(BaseModel):
    flight_id: str
    battery_level: Optional[float] = None
    distance: float = 0
    detections: int = 0

class TelemetryDTO(BaseModel):
    flight_id: str
    battery_level: Optional[float] = None
    distance: float = 0
    detections: int = 0
```

### `webapp/backend/dtos/chase_event_dto.py`
```python
from pydantic import BaseModel
from typing import Optional

class ChaseEventCreateDTO(BaseModel):
    flight_id: str
    detection_image_id: Optional[int] = None
    counter_measure_type: str  # "pursuit", "movement", "combined"

class ChaseEventDTO(BaseModel):
    id: int
    flight_id: str
    detection_image_id: Optional[int] = None
    start_time: str
    end_time: Optional[str] = None
    counter_measure_type: str
    outcome: Optional[str] = None  # "dispersed", "lost", "aborted"
```

### `webapp/backend/dtos/detection_dto.py`
```python
from pydantic import BaseModel
from typing import Optional

class DetectionImageDTO(BaseModel):
    id: int
    flight_id: str
    image_path: str
    timestamp: str

class DetectionConfigDTO(BaseModel):
    confidence_threshold: float = 0.3
    model_path: Optional[str] = None

class DetectionStatusDTO(BaseModel):
    running: bool
    flight_id: Optional[str] = None
    detection_count: int = 0
```

---

## Phase 1b: Repositories

Create `webapp/backend/repositories/` package. Each repository wraps one table.

### `webapp/backend/repositories/__init__.py`
Export all repositories.

### `webapp/backend/repositories/base.py`
```python
import sqlite3
from webapp.backend.database.db import get_db

class BaseRepository:
    def _get_conn(self) -> sqlite3.Connection:
        return get_db()
```

### `webapp/backend/repositories/flight_repository.py`

Methods (extract from current db.py):
- `create(area_map_id: Optional[int] = None) -> FlightDTO`
- `get_by_id(flight_id: str) -> Optional[FlightDTO]`
- `get_all() -> list[FlightDTO]`
- `update(flight_id: str, **kwargs) -> None`
- `delete(flight_id: str) -> bool`
- `end_flight(flight_id: str, pigeons: int, frames: int, video_path: Optional[str]) -> None`
- `fail_flight(flight_id: str) -> None`

### `webapp/backend/repositories/area_map_repository.py`

Methods:
- `create(dto: AreaMapCreateDTO) -> AreaMapDTO`
- `get_by_id(area_map_id: int) -> Optional[AreaMapDTO]`
- `get_all() -> list[AreaMapDTO]`
- `update(area_map_id: int, **kwargs) -> None`
- `delete(area_map_id: int) -> bool`
- `get_flights_for_area(area_map_id: int) -> list[FlightDTO]`

### `webapp/backend/repositories/telemetry_repository.py`

Methods:
- `create(dto: TelemetryCreateDTO) -> TelemetryDTO`
- `get_by_flight_id(flight_id: str) -> Optional[TelemetryDTO]`
- `update(flight_id: str, **kwargs) -> None`

### `webapp/backend/repositories/chase_event_repository.py`

Methods:
- `create(dto: ChaseEventCreateDTO) -> ChaseEventDTO`
- `get_by_id(chase_id: int) -> Optional[ChaseEventDTO]`
- `get_by_flight_id(flight_id: str) -> list[ChaseEventDTO]`
- `update(chase_id: int, **kwargs) -> None`

### `webapp/backend/repositories/detection_image_repository.py`

Methods (extract from current db.py):
- `create(flight_id: str, image_path: str) -> DetectionImageDTO`
- `get_by_flight_id(flight_id: str) -> list[DetectionImageDTO]`

---

## Phase 1c: Services

Refactor and add services in `webapp/backend/services/`.

### Keep existing (minor refactor)
- `sim_service.py` -- no changes needed
- `detection_service.py` -- change `add_detection_image()` call to use `DetectionImageRepository`

### New services

**`webapp/backend/services/flight_service.py`**

Absorbs flight lifecycle logic from `app.py`:
- `create_flight(area_map_id: Optional[int] = None) -> FlightDTO`
- `start_detection(flight_id: str, on_detection: Callable) -> bool` -- delegates to DetectionService
- `stop_flight(flight_id: str) -> FlightDTO` -- stops detection, ends flight
- `abort_flight(flight_id: str) -> FlightDTO` -- immediate stop
- `get_flight(flight_id: str) -> Optional[FlightDTO]`
- `get_all_flights() -> list[FlightDTO]`
- `get_flight_summary(flight_id: str) -> FlightSummaryDTO`
- `delete_flight(flight_id: str) -> bool`

Uses: `FlightRepository`, `TelemetryRepository`, `DetectionService`

**`webapp/backend/services/drone_service.py`**

Wraps drone subprocess state:
- `get_status() -> dict` -- is connected, is flying, mode, battery
- `start_flight(flight_id: str) -> bool` -- spawn flight subprocess
- `stop_flight() -> dict` -- stop subprocess gracefully
- `abort() -> bool` -- kill subprocess, trigger emergency landing
- `return_home() -> bool` -- command RTL
- `get_telemetry() -> dict` -- latest parsed telemetry from subprocess stdout

**`webapp/backend/services/area_map_service.py`**

CRUD + mapping session:
- `create_map(dto: AreaMapCreateDTO) -> AreaMapDTO`
- `get_map(map_id: int) -> Optional[AreaMapDTO]`
- `get_all_maps() -> list[AreaMapDTO]`
- `update_map(map_id: int, **kwargs) -> None`
- `delete_map(map_id: int) -> bool`
- `start_mapping(name: str) -> dict` -- spawn mapping flight subprocess
- `get_mapping_status() -> dict`

**`webapp/backend/services/chase_event_service.py`**

Chase event lifecycle:
- `start_chase(flight_id: str, detection_image_id: Optional[int], measure_type: str) -> ChaseEventDTO`
- `end_chase(chase_id: int, outcome: str) -> ChaseEventDTO`
- `get_chases_for_flight(flight_id: str) -> list[ChaseEventDTO]`
- `get_chase(chase_id: int) -> Optional[ChaseEventDTO]`

**`webapp/backend/services/telemetry_service.py`**

Telemetry recording:
- `init_telemetry(flight_id: str) -> TelemetryDTO`
- `update_telemetry(flight_id: str, battery: Optional[float], distance: float, detections: int) -> None`
- `get_telemetry(flight_id: str) -> Optional[TelemetryDTO]`

**`webapp/backend/services/recording_service.py`**

Video recording management:
- `start_recording(flight_id: str) -> bool`
- `stop_recording() -> Optional[str]` -- returns video path
- `get_status() -> dict`

---

## Phase 1d: API Controllers (Router Refactor)

Split `app.py` into routers. Create `webapp/backend/controllers/` package.

### `webapp/backend/controllers/sim_controller.py`
Move `/api/sim/*` routes from app.py. Keep existing logic.

### `webapp/backend/controllers/connection_controller.py`
New routes (ADD A.2):
- `GET /api/connection/wifi` -- return mock `{"connected": true, "ssid": "simulation"}`
- `POST /api/connection/ssh` -- return mock `{"success": true}`
- `DELETE /api/connection/ssh` -- return mock `{"success": true}`
- `GET /api/connection/status` -- aggregate wifi/ssh/drone/stream status
- `POST /api/connection/video/start` -- delegates to RecordingService
- `POST /api/connection/video/stop` -- delegates to RecordingService

### `webapp/backend/controllers/drone_controller.py`
New routes (ADD A.3):
- `GET /api/drone/status` -- DroneService.get_status()
- `POST /api/drone/start` -- DroneService.start_flight()
- `POST /api/drone/stop` -- DroneService.stop_flight()
- `POST /api/drone/abort` -- DroneService.abort()
- `POST /api/drone/return-home` -- DroneService.return_home()
- `GET /api/drone/telemetry` -- DroneService.get_telemetry()
- `WS /api/drone/telemetry/stream` -- WebSocket pushing telemetry updates

### `webapp/backend/controllers/flight_controller.py`
Move + extend `/api/flights/*` routes (ADD A.4):
- `GET /api/flights` -- FlightService.get_all_flights()
- `GET /api/flights/{id}` -- FlightService.get_flight()
- `GET /api/flights/{id}/summary` -- FlightService.get_flight_summary()
- `GET /api/flights/{id}/images` -- existing logic
- `GET /api/flights/{id}/recording` -- existing logic
- `GET /api/flights/{id}/telemetry` -- TelemetryService.get_telemetry()
- `DELETE /api/flights/{id}` -- FlightService.delete_flight()

### `webapp/backend/controllers/area_map_controller.py`
New routes (ADD A.5):
- `GET /api/areas` -- AreaMapService.get_all_maps()
- `GET /api/areas/{id}` -- AreaMapService.get_map()
- `POST /api/areas` -- AreaMapService.create_map()
- `PUT /api/areas/{id}` -- AreaMapService.update_map()
- `DELETE /api/areas/{id}` -- AreaMapService.delete_map()
- `GET /api/areas/{id}/flights` -- AreaMapService.get_flights_for_area() (via repo)
- `POST /api/areas/mapping/start` -- AreaMapService.start_mapping()
- `GET /api/areas/mapping/status` -- AreaMapService.get_mapping_status()

### `webapp/backend/controllers/detection_controller.py`
New routes (ADD A.6):
- `GET /api/detection/status` -- DetectionService status
- `GET /api/detection/config` -- current confidence threshold, model path
- `PUT /api/detection/config` -- update threshold

### `webapp/backend/controllers/chase_event_controller.py`
New routes (ADD A.7):
- `GET /api/flights/{id}/chases` -- ChaseEventService.get_chases_for_flight()
- `GET /api/chases/{id}` -- ChaseEventService.get_chase()

### Refactor `app.py`

Slim down to:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from webapp.backend.controllers import (
    sim_controller, connection_controller, drone_controller,
    flight_controller, area_map_controller, detection_controller,
    chase_event_controller,
)

app = FastAPI(title="Scarecrow Drone")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(sim_controller.router)
app.include_router(connection_controller.router)
app.include_router(drone_controller.router)
app.include_router(flight_controller.router)
app.include_router(area_map_controller.router)
app.include_router(detection_controller.router)
app.include_router(chase_event_controller.router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

Keep the file serving endpoints (/detection_images/*, /recordings/*) in app.py or a separate static_controller.

## Verification

1. `python -c "from webapp.backend.app import app"` -- imports without error
2. Start server: `uvicorn webapp.backend.app:app --port 8000`
3. `curl http://localhost:8000/api/health` -- returns OK
4. `curl http://localhost:8000/api/flights` -- returns existing data
5. `curl http://localhost:8000/api/areas` -- returns empty list
6. `curl http://localhost:8000/api/drone/status` -- returns status
7. All existing webapp functionality still works (connect sim, start/stop flight, view history)
