# Phase 6: UC7 — Abort Mission & Return Home

**Dependencies**: Phase 4 (detection flight running via subprocess)
**Estimated size**: Small
**Simulation required**: Yes (to verify safe landing)

## Context (from ADD)

**UC7 — Abort Mission** is the safety system. The operator clicks "Abort Mission" on the dashboard during an active flight. The system immediately terminates all operations (detection, recording, chase), commands the drone to return home or land, and updates the flight record to "aborted".

### ADD Sequence (Section 4.1.7)
```
Operator -> Dashboard: Click "Abort Mission"
Dashboard -> FlightController: POST /api/flights/{id}/abort
FlightController -> FlightService: abort_flight()
FlightService -> DroneService: stop_operations()
DroneService -> DroneService: stop_recording()
DroneService -> DroneService: return_home()
FlightService -> DB: UPDATE flights SET status='aborted'
FlightController -> Dashboard: 200 OK, Flight object
Dashboard -> Operator: "Mission Aborted"
```

### ADD Abort Event (Section 4.2)
```
Flight Aborted:
  Trigger: Operator clicks "Abort Mission" or system error
  Response:
    - Immediately stop all operations
    - Drone returns home or lands
    - Save partial data
    - Set flight status to "aborted"
    - Alert operator
  State Changes:
    - Flight: in_progress -> aborted
    - Drone: any_state -> returning_home
    - Video: recording -> stopped
    - Detection: active -> idle
```

### ADD Alternate Courses
```
A1. Communication Lost:
  - Drone activates failsafe mode
  - Drone auto-lands or returns home
  - System retries connection
A2. Low Battery During Abort:
  - Drone prioritizes immediate landing
  - System logs emergency landing event
```

---

## Existing Code to Reuse

| What | File | How |
|------|------|-----|
| DetectionService.stop() | `webapp/backend/services/detection_service.py` | Detaches from subprocess (doesn't kill it) |
| subprocess.Popen | `webapp/backend/services/detection_service.py` | .process reference to the running flight |
| Flight DB functions | `webapp/backend/database/db.py` | fail_flight() sets status and end_time |
| demo_flight.py landing | `scripts/flight/demo_flight.py` lines ~280+ | Emergency landing pattern |
| MAVSDK action.land() | Used in all flight scripts | Safe landing command |

---

## New Code

### 1. SIGTERM Handler in Flight Scripts

**File**: Modify ALL flight scripts (`demo_flight.py`, `room_circuit.py`, `map_area.py`, any new patrol script)

Add at the top of each script:

```python
import signal

_abort_requested = False

def _sigterm_handler(signum, frame):
    global _abort_requested
    _abort_requested = True
    print("ABORT_REQUESTED", flush=True)

signal.signal(signal.SIGTERM, _sigterm_handler)
```

In the flight loop, check the flag:

```python
# In the main flight loop:
while flight_active:
    if _abort_requested:
        print("ABORT: Emergency landing initiated", flush=True)
        break

    # ... normal flight logic ...

# After the loop (in the finally block):
# The existing try/finally in demo_flight.py already handles landing:
finally:
    print("Landing...")
    await drone.offboard.set_velocity_body(VelocityBodyYawspeed(0, 0, 0, 0))
    try:
        await drone.offboard.stop()
    except:
        pass
    await drone.action.land()
    lidar.stop()
    camera.stop()
    # ... cleanup ...
```

**Key point**: The flight script handles its own landing. The webapp just sends SIGTERM and waits.

### 2. DroneService.abort()

**File**: `webapp/backend/services/drone_service.py` (extend from Phase 1)

```python
import signal

class DroneService:
    def abort(self) -> bool:
        """Abort the current flight. Send SIGTERM to flight subprocess."""
        if not self._process or self._process.poll() is not None:
            return False  # no active process

        # Send SIGTERM — flight script handles graceful landing
        self._process.send_signal(signal.SIGTERM)

        # Wait up to 30 seconds for graceful shutdown
        try:
            self._process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Force kill if script didn't exit
            self._process.kill()
            self._process.wait(timeout=5)

        return True

    def return_home(self) -> bool:
        """Command return to home. Same as abort for simulation."""
        # In simulation, return_home = abort (land at current position)
        # On real hardware: would send RTL command via MAVSDK
        return self.abort()
```

### 3. FlightService.abort_flight()

**File**: `webapp/backend/services/flight_service.py` (extend from Phase 1)

```python
def abort_flight(self, flight_id: str) -> Optional[FlightDTO]:
    """Abort an active flight."""
    flight = self.flight_repo.get_by_id(flight_id)
    if not flight or flight.status != "in_progress":
        return None

    # Stop the drone subprocess
    self.drone_service.abort()

    # Update flight record
    self.flight_repo.update(
        flight_id,
        status="aborted",
        end_time=datetime.now().isoformat(),
    )

    # Update telemetry with final values
    self.telemetry_service.update_telemetry(
        flight_id,
        battery=self.drone_service.latest_telemetry.get("battery"),
        distance=self.drone_service.latest_telemetry.get("distance", 0),
        detections=self.drone_service.latest_telemetry.get("detections", 0),
    )

    return self.flight_repo.get_by_id(flight_id)
```

### 4. API Endpoints

**File**: `webapp/backend/controllers/drone_controller.py` (from Phase 1)

```python
@router.post("/api/drone/abort")
async def abort_mission():
    """Emergency abort current flight."""
    flight_id = drone_service.current_flight_id
    if not flight_id:
        raise HTTPException(400, "No active flight")

    result = flight_service.abort_flight(flight_id)
    if not result:
        raise HTTPException(500, "Abort failed")

    return {"success": True, "flight": result.model_dump()}

@router.post("/api/drone/return-home")
async def return_home():
    """Command drone to return home and land."""
    success = drone_service.return_home()
    if not success:
        raise HTTPException(400, "No active flight or drone not responding")
    return {"success": True}
```

### 5. Frontend Abort Button

**File**: Modify `webapp/frontend/src/components/SimControl.tsx`

Add a red abort button visible only during active flight:

```tsx
{flightStatus?.isFlying && (
    <button
        className="abort-btn"
        onClick={async () => {
            if (window.confirm("Abort mission? Drone will land immediately.")) {
                await api.abortDrone();
            }
        }}
    >
        ABORT MISSION
    </button>
)}
```

**CSS** in `App.css`:
```css
.abort-btn {
    background: #dc3545;
    color: white;
    font-weight: bold;
    font-size: 1.1em;
    padding: 12px 24px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    margin-top: 16px;
    width: 100%;
}
.abort-btn:hover {
    background: #c82333;
}
```

---

## Implementation Notes

### Why SIGTERM and not a file/socket signal?

- SIGTERM is the standard Unix way to request graceful shutdown
- The flight script already runs as a subprocess — it has a PID
- No need for a shared file, socket, or other IPC mechanism
- Python's signal module handles it cleanly
- The flight script's existing try/finally block catches KeyboardInterrupt — SIGTERM triggers the same cleanup path

### What about MAVSDK failsafe?

PX4 has built-in failsafe modes (auto-land on RC loss, return-to-launch on data link loss). These are separate from the webapp abort:
- Webapp abort = operator-initiated, graceful
- PX4 failsafe = automatic, triggered by hardware conditions

For the university demo, the webapp abort is sufficient. PX4 failsafe is configured in the airframe parameters and works independently.

### What about partial data?

When a flight is aborted:
- Detection images already saved are preserved (they're written to disk immediately)
- Video recording may be incomplete — the save_video() call in the flight script's finally block will still stitch whatever frames were captured
- Telemetry is updated with last known values
- Chase events in progress get outcome="aborted"

---

## Verification

### Unit test (no sim)
```python
def test_abort_sets_status():
    # Create a flight, abort it, verify status
    flight = flight_service.create_flight()
    flight_service.abort_flight(flight.id)
    result = flight_repo.get_by_id(flight.id)
    assert result.status == "aborted"
    assert result.end_time is not None
```

### Subprocess SIGTERM test (no sim)
```python
import subprocess, signal, time

# Start a dummy long-running script
proc = subprocess.Popen(["python3", "-c", """
import signal, time
def handler(s, f):
    print("ABORT_REQUESTED", flush=True)
    exit(0)
signal.signal(signal.SIGTERM, handler)
while True: time.sleep(1)
"""], stdout=subprocess.PIPE, text=True)

time.sleep(0.5)
proc.send_signal(signal.SIGTERM)
proc.wait(timeout=5)
output = proc.stdout.read()
assert "ABORT_REQUESTED" in output
```

### Full sim test
```bash
# 1. Launch sim
source scripts/shell/env.sh && ./scripts/shell/launch.sh drone_garage

# 2. Start flight via webapp or CLI
source .venv-mavsdk/bin/activate
python3 scripts/flight/demo_flight.py &
FLIGHT_PID=$!

# 3. Wait for takeoff (watch stdout for "Hovering...")
sleep 15

# 4. Send SIGTERM
kill -TERM $FLIGHT_PID

# 5. Watch output — should see:
#    ABORT_REQUESTED
#    ABORT: Emergency landing initiated
#    Landing...
#    (drone lands safely)

# 6. Verify process exited
wait $FLIGHT_PID
echo "Exit code: $?"
```

### Webapp abort test
```bash
# 1. Start webapp + sim
cd webapp && ./start.sh
# 2. Connect sim, start detection flight
# 3. While drone is flying, click red "ABORT MISSION" button
# 4. Confirm dialog
# 5. Drone should land within 30 seconds
# 6. Flight history shows status "aborted"
# 7. Detection images from before abort are preserved
```
