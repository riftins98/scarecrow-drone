# Phase 3: UC1 — Map Area Operation

**Dependencies**: Phase 2 (Drone, NavigationUnit, MapUnit classes)
**Estimated size**: Medium
**Simulation required**: Yes (PX4 + Gazebo with indoor_room world)

## Context (from ADD)

**UC1 — Map Area Operation** is the first step before any detection flight. The operator initiates a mapping flight from the webapp. The drone flies a systematic area scan, captures terrain/boundary data via lidar, and stores the result as an AreaMap record. Future detection flights use this map to define patrol routes and flight boundaries.

### ADD Sequence (Section 4.1.1)
```
Operator -> Dashboard: Navigate to Mapping page
Operator -> Dashboard: Click "Start Mapping"
Dashboard -> Controller: POST /api/areas/mapping/start
Controller -> Service: start_mapping()
Service -> AreaMap: create_map()
AreaMap -> DB: INSERT area_maps
DB -> AreaMap: ID
Service -> [Spawn mapping flight subprocess]
... drone flies circuit, records lidar at each corner ...
Flight subprocess -> stdout: MAP_RESULT:{json}
Service: parse result, UPDATE area_maps with boundaries + area_size
Dashboard: poll /api/areas/mapping/status for progress
Operator: review mapped boundaries
```

### ADD State Machine (Section 4.2 Events)
```
AreaMap: draft -> mapping_in_progress -> processing -> active
                                      -> draft (if aborted)
```

### ADD Data Model (Section 3.2.1)
```
area_maps:
  id          INTEGER PRIMARY KEY AUTOINCREMENT
  name        TEXT NOT NULL
  created_at  TEXT NOT NULL
  updated_at  TEXT NOT NULL
  boundaries  TEXT (JSON string with coordinate points)
  area_size   REAL (square meters)
  status      TEXT ('draft', 'active', 'mapping_in_progress', 'processing')
```

---

## Existing Code to Reuse

| What | File | How to reuse |
|------|------|-------------|
| Room circuit pattern | `scripts/flight/room_circuit.py` | fly_leg() + do_turn() loop = the mapping flight pattern |
| Wall follow controller | `scarecrow/controllers/wall_follow.py` | WallFollowController for each circuit leg |
| Rotation | `scarecrow/controllers/rotation.py` | rotate_90() at corners |
| Lidar stabilization | `scarecrow/flight/stabilization.py` | lidar_stabilize() after turns |
| Distance stabilizer | `scarecrow/controllers/distance_stabilizer.py` | DistanceStabilizerController for corner stabilization |
| Front wall detector | `scarecrow/controllers/front_wall_detector.py` | FrontWallDetector for wall-follow stop condition |
| Gazebo lidar | `scarecrow/sensors/lidar/gazebo.py` | GazeboLidar for scan data |
| Flight helpers | `scarecrow/flight/helpers.py` | get_position, wait_for_altitude, wait_for_stable |
| Subprocess pattern | `webapp/backend/services/detection_service.py` | How to spawn and monitor a flight subprocess |
| MapUnit | `scarecrow/navigation/map_unit.py` | Records positions + computes boundaries (from Phase 2) |
| NavigationUnit | `scarecrow/navigation/navigation_unit.py` | wall_follow + rotate facade (from Phase 2) |
| Drone class | `scarecrow/drone.py` | Connect, arm, takeoff, offboard, land (from Phase 2) |

---

## New Code

### 1. Mapping Flight Script

**File**: `scripts/flight/map_area.py`

This is the drone-side script. Spawned as subprocess by AreaMapService. Communicates results via stdout protocol.

**Stdout protocol** (parsed by AreaMapService._monitor()):
- `MAP_STATUS:scanning` — currently flying and recording
- `MAP_STATUS:leg_N` — completed leg N of circuit
- `MAP_POINT:{"x":1.2,"y":3.4,"front":5.0,"rear":7.0,"left":2.0,"right":8.0}` — recorded measurement
- `MAP_RESULT:{"boundaries":"[...]","area_size":42.5}` — final result (triggers DB update)
- `MAP_ERROR:description` — error occurred

**Flight sequence**:
```
1. Parse args: --map-name <name>, --num-legs <4>, --wall-side <right>, --wall-distance <2.0>
2. Connect to drone (Drone class)
3. Start lidar (GazeboLidar)
4. Arm + takeoff to 2.5m
5. Start offboard mode
6. Start MapUnit.start_mapping()
7. Record initial position: MapUnit.record_position(scan, position)
8. For each leg (1..num_legs):
   a. Print MAP_STATUS:leg_N
   b. wall_follow(side, target_distance) until front wall
   c. Record position at wall: MapUnit.record_position(scan, position)
   d. Print MAP_POINT:{json}
   e. If not last leg: rotate 90 degrees, stabilize
9. Finish mapping: result = MapUnit.finish_mapping()
10. Print MAP_RESULT:{json.dumps(result)}
11. Stop offboard, land, stop lidar
```

**SIGTERM handling**: If aborted, print `MAP_ERROR:aborted`, land immediately.

**Key implementation detail**: Copy the connection + takeoff + landing pattern EXACTLY from `scripts/flight/room_circuit.py` lines 60-160. Don't rewrite — the timing, error handling, and parameter verification are proven to work.

### 2. AreaMapService Extension

**File**: `webapp/backend/services/area_map_service.py` (extend from Phase 1)

Add mapping subprocess management (follow DetectionService pattern exactly):

```python
def start_mapping(self, name: str) -> dict:
    """Spawn mapping flight subprocess."""
    if self._mapping_active:
        return {"success": False, "error": "Mapping already in progress"}

    # Create area_map record with status='mapping_in_progress'
    area_map = self.repo.create(AreaMapCreateDTO(name=name))
    self._current_map_id = area_map.id
    self.repo.update(area_map.id, status="mapping_in_progress")

    # Spawn subprocess (same pattern as DetectionService.start())
    script = os.path.join(REPO_ROOT, "scripts", "flight", "map_area.py")
    self._process = subprocess.Popen(
        ["python3", script, "--map-name", name],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=self._get_env(), cwd=REPO_ROOT,
    )
    self._mapping_active = True

    # Monitor thread (same pattern as DetectionService._monitor())
    t = threading.Thread(target=self._monitor_mapping, daemon=True)
    t.start()

    return {"success": True, "mappingId": area_map.id}

def _monitor_mapping(self):
    """Parse stdout from mapping subprocess."""
    try:
        for line in self._process.stdout:
            line = line.strip()
            if line.startswith("MAP_RESULT:"):
                result = json.loads(line.split("MAP_RESULT:", 1)[1])
                self.repo.update(
                    self._current_map_id,
                    boundaries=result["boundaries"],
                    area_size=result["area_size"],
                    status="active",
                    updated_at=datetime.now().isoformat(),
                )
            elif line.startswith("MAP_ERROR:"):
                self.repo.update(self._current_map_id, status="draft")
            elif line.startswith("MAP_STATUS:"):
                self._mapping_status = line.split(":", 1)[1]
    finally:
        self._mapping_active = False

def get_mapping_status(self) -> dict:
    return {
        "active": self._mapping_active,
        "mapId": self._current_map_id,
        "status": self._mapping_status,
    }
```

### 3. API Endpoints

Already defined in Phase 1 `area_map_controller.py`. Ensure these work:
- `POST /api/areas/mapping/start` — body: `{"name": "Room A"}` — calls `AreaMapService.start_mapping()`
- `GET /api/areas/mapping/status` — calls `AreaMapService.get_mapping_status()`
- `GET /api/areas` — lists all area maps
- `GET /api/areas/{id}` — get single map with boundaries

---

## Simulation Setup

**World**: `indoor_room.sdf` or `drone_garage.sdf`

**Launch**:
```bash
source scripts/shell/env.sh
./scripts/shell/launch.sh indoor_room
```

**Known issue**: Drone crashes in indoor_room after ~4s due to wall drift. If this persists, test with drone_garage (larger space, more stable) and adjust wall_distance targets.

**Alternative for testing without full sim**: Run just the MapUnit logic with mock data to verify boundary computation, then test the full flight in sim.

---

## Verification

### Unit test (no sim needed)
```python
# Test MapUnit boundary computation
from scarecrow.navigation.map_unit import MapUnit, MappingPoint

mapper = MapUnit()
mapper.start_mapping()
# Simulate 4 corners of a 10x8m room
mapper.record_position(mock_scan(front=8, rear=2, left=2, right=8), north_m=0, east_m=0)
mapper.record_position(mock_scan(front=2, rear=8, left=2, right=8), north_m=8, east_m=0)
mapper.record_position(mock_scan(front=2, rear=8, left=8, right=2), north_m=8, east_m=8)
mapper.record_position(mock_scan(front=8, rear=2, left=8, right=2), north_m=0, east_m=8)
result = mapper.finish_mapping()
assert result["area_size"] > 0
assert "boundaries" in result
```

### Integration test (no sim needed)
```bash
# Test API endpoints
curl -X POST http://localhost:8000/api/areas -H "Content-Type: application/json" -d '{"name":"Test Room"}'
curl http://localhost:8000/api/areas
```

### Full sim test
```bash
# 1. Launch sim
source scripts/shell/env.sh && ./scripts/shell/launch.sh drone_garage

# 2. In pxh> console: set EKF origin
commander set_gps_global_origin 0 0 0

# 3. Run mapping flight
source .venv-mavsdk/bin/activate
python3 scripts/flight/map_area.py --map-name "Garage Test"

# 4. Verify output
# Should see MAP_STATUS:leg_1 through leg_4, then MAP_RESULT:{...}
# Check DB: sqlite3 webapp/backend/database/scarecrow.db "SELECT * FROM area_maps"
```

### Webapp test
```bash
# 1. Start backend + frontend
cd webapp && ./start.sh

# 2. In browser: connect sim, navigate to Area Maps page
# 3. Click "Start Mapping", enter name
# 4. Watch status updates
# 5. After completion: map should appear in list with boundaries and area size
```
