# Phase 5: UC5 — Chase Birds & Apply Counter Measures

**Dependencies**: Phase 4 (detection flight working with YOLO)
**Estimated size**: Large
**Simulation required**: Yes (PX4 + Gazebo with drone_garage + pigeon_billboard)

## Context (from ADD)

**UC5 — Chase Birds & Apply Counter Measures** is the core autonomous behavior. When YOLO detects a bird during a patrol flight, the drone interrupts its patrol, calculates a pursuit trajectory toward the detection, flies toward it, applies counter-measures (aggressive movement to scare the bird), monitors whether the bird dispersed, then returns to patrol.

### ADD Sequence (Section 4.1.5)
```
DetectionService: bird_detected()
  -> DroneController: initiate_chase()
    -> DroneService: initiate_chase()
      -> ChaseEvent: log_chase()         -> DB: INSERT chase_events -> chase_id
      -> DroneService: calculate_trajectory()
      -> DroneService: move_to_location()
      -> DroneService: activate_countermeasure()
      -> DroneService: return_to_patrol()
      -> ChaseEvent: set_outcome()       -> DB: UPDATE chase_events
```

### ADD Chase State Machine (Section 4.3.4)
```
Patrolling
  |-- Bird Detected --> Calculating Trajectory
                          |-- Trajectory Ready --> Pursuing Birds
                          |-- Birds Out of Range --> Patrolling
                        Pursuing Birds
                          |-- Reached Target --> Applying Counter-Measures
                          |-- Battery Low --> Returning to Patrol
                          |-- Flight Aborted --> Patrolling
                        Applying Counter-Measures
                          |-- Complete --> Monitoring Birds
                        Monitoring Birds
                          |-- Birds Dispersed --> Returning to Patrol
                          |-- Birds Lost (out of view) --> Returning to Patrol
                          |-- Birds Still Present --> Pursuing Birds (re-engage)
                        Returning to Patrol
                          |-- Back at Route --> Patrolling
```

### ADD Event Table (Section 4.2 — chase events)
```
Chase Initiated:    Create chase record, calculate trajectory, log start time
Chase Completed:    Stop pursuit, return to patrol, update chase record
Birds Dispersed:    outcome="dispersed", return to patrol
Birds Lost:         outcome="lost", return to patrol
Counter-Measure (Pursuit):  Aggressive pursuit movement
Counter-Measure (Movement): Aggressive flight maneuver pattern
```

### ADD chase_events Table (Section 3.2.5)
```
id                   INTEGER PRIMARY KEY
flight_id            TEXT NOT NULL (FK -> flights)
detection_image_id   INTEGER (FK -> detection_images, nullable)
start_time           TEXT NOT NULL
end_time             TEXT (nullable while in progress)
counter_measure_type TEXT NOT NULL ('pursuit', 'movement', 'combined')
outcome              TEXT (nullable: 'dispersed', 'lost', 'aborted')
```

---

## Existing Code to Reuse

| What | File | How |
|------|------|-----|
| YoloDetector with callbacks | `scarecrow/detection/yolo.py` | on_detection callback triggers chase |
| VelocityCommand | `scarecrow/controllers/wall_follow.py` | Reuse dataclass for chase velocity output |
| GazeboCamera on_frame | `scarecrow/sensors/camera/gazebo.py` | Feeds frames to YOLO during patrol AND chase |
| DetectionService stdout parsing | `webapp/backend/services/detection_service.py` | Pattern for parsing CHASE_START/CHASE_END |
| Offboard velocity control | `scarecrow/flight/stabilization.py` | set_velocity_body pattern for chase movement |
| demo_flight.py flight loop | `scripts/flight/demo_flight.py` | Extend the hover/patrol loop with chase interrupt |

---

## New Code

### 1. ChaseController

**File**: `scarecrow/chase/__init__.py` (empty)
**File**: `scarecrow/chase/chase_controller.py`

The core algorithm: converts a YOLO detection's pixel position into a drone velocity command to fly toward the bird.

```python
"""Chase controller — converts bird detection to pursuit velocity commands.

The chase has 3 phases:
1. Pursuit: fly toward the detection's pixel center (yaw + forward)
2. Counter-measure: aggressive hover/buzz at target location
3. Monitor: check if bird left the frame

Design: proportional control from pixel offset to yaw rate.
The bird's horizontal pixel position determines yaw, forward speed is constant.
Vertical position is ignored (altitude stays constant during chase).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..controllers.wall_follow import VelocityCommand


class ChaseState(Enum):
    IDLE = "idle"
    PURSUING = "pursuing"
    APPLYING_COUNTERMEASURE = "applying_countermeasure"
    MONITORING = "monitoring"
    COMPLETED = "completed"


@dataclass
class DetectionTarget:
    """A detected bird's position in the camera frame."""
    center_x: int          # pixel x (0 = left edge of frame)
    center_y: int          # pixel y (0 = top edge of frame)
    frame_width: int = 640
    frame_height: int = 480
    confidence: float = 0.0
    detection_image_id: Optional[int] = None


class ChaseController:
    """State machine controller for bird pursuit and counter-measures.

    Usage:
        chase = ChaseController()
        chase.start(target)
        while not chase.is_complete:
            cmd = chase.update(current_detections_or_none)
            await drone.set_velocity(cmd)

    Args:
        yaw_gain: Yaw rate per pixel of horizontal offset (deg/s per pixel).
        forward_speed: Constant forward speed during pursuit (m/s).
        max_yaw_speed: Maximum yaw correction speed (deg/s).
        pursuit_timeout: Max seconds to pursue before giving up (outcome='lost').
        countermeasure_duration: Seconds of aggressive movement at target.
        monitor_duration: Seconds to watch after counter-measure.
        countermeasure_type: Type of counter-measure ('pursuit', 'movement', 'combined').
    """

    def __init__(
        self,
        yaw_gain: float = 0.15,
        forward_speed: float = 0.3,
        max_yaw_speed: float = 20.0,
        pursuit_timeout: float = 10.0,
        countermeasure_duration: float = 3.0,
        monitor_duration: float = 2.0,
        countermeasure_type: str = "pursuit",
    ):
        self.yaw_gain = yaw_gain
        self.forward_speed = forward_speed
        self.max_yaw_speed = max_yaw_speed
        self.pursuit_timeout = pursuit_timeout
        self.countermeasure_duration = countermeasure_duration
        self.monitor_duration = monitor_duration
        self.countermeasure_type = countermeasure_type

        self.state = ChaseState.IDLE
        self.outcome: Optional[str] = None
        self._target: Optional[DetectionTarget] = None
        self._state_start: float = 0.0
        self._chase_start: float = 0.0

    @property
    def is_complete(self) -> bool:
        return self.state == ChaseState.COMPLETED

    def start(self, target: DetectionTarget) -> None:
        """Begin a chase sequence toward a detected bird."""
        self._target = target
        self.state = ChaseState.PURSUING
        self.outcome = None
        self._chase_start = time.time()
        self._state_start = time.time()

    def update(self, current_detection: Optional[DetectionTarget] = None) -> VelocityCommand:
        """Compute next velocity command based on chase state.

        Args:
            current_detection: Latest YOLO detection if bird still visible, None if lost.

        Returns:
            VelocityCommand for the drone.
        """
        now = time.time()
        elapsed_in_state = now - self._state_start
        elapsed_total = now - self._chase_start

        if self.state == ChaseState.PURSUING:
            # Timeout: bird escaped
            if elapsed_total > self.pursuit_timeout:
                self._complete("lost")
                return VelocityCommand()

            if current_detection is not None:
                # Update target with latest position
                self._target = current_detection

                # Check if close enough (bird near center = close)
                x_offset = abs(current_detection.center_x - current_detection.frame_width / 2)
                if x_offset < 50:  # bird roughly centered = reached target
                    self.state = ChaseState.APPLYING_COUNTERMEASURE
                    self._state_start = now
                    return VelocityCommand()

                # Fly toward bird
                return self._compute_pursuit(current_detection)
            else:
                # Bird lost from frame — keep moving forward briefly
                if elapsed_in_state > 3.0:
                    self._complete("lost")
                    return VelocityCommand()
                return VelocityCommand(forward_m_s=self.forward_speed * 0.5)

        elif self.state == ChaseState.APPLYING_COUNTERMEASURE:
            if elapsed_in_state >= self.countermeasure_duration:
                self.state = ChaseState.MONITORING
                self._state_start = now
                return VelocityCommand()

            # Counter-measure: aggressive yaw movement to scare bird
            # Oscillate yaw rapidly
            yaw = 15.0 if (int(elapsed_in_state * 4) % 2 == 0) else -15.0
            return VelocityCommand(yawspeed_deg_s=yaw)

        elif self.state == ChaseState.MONITORING:
            if elapsed_in_state >= self.monitor_duration:
                if current_detection is not None:
                    # Bird still there — re-engage
                    self.state = ChaseState.PURSUING
                    self._state_start = now
                    return self._compute_pursuit(current_detection)
                else:
                    self._complete("dispersed")
                    return VelocityCommand()

            # Hover and observe
            return VelocityCommand()

        # IDLE or COMPLETED
        return VelocityCommand()

    def _compute_pursuit(self, target: DetectionTarget) -> VelocityCommand:
        """Proportional yaw control toward target pixel position."""
        x_offset = target.center_x - (target.frame_width / 2)
        yaw = self.yaw_gain * x_offset
        yaw = max(-self.max_yaw_speed, min(self.max_yaw_speed, yaw))
        return VelocityCommand(
            forward_m_s=self.forward_speed,
            yawspeed_deg_s=yaw,
        )

    def _complete(self, outcome: str) -> None:
        self.state = ChaseState.COMPLETED
        self.outcome = outcome
```

### 2. Integrate Chase into Flight Script

**File**: Modify `scripts/flight/demo_flight.py` (or create `scripts/flight/patrol_detect_chase.py`)

The key integration: YoloDetector's on_detection callback triggers a chase interrupt.

```python
# In the flight script, during patrol/hover loop:

chase_ctrl = ChaseController(
    pursuit_timeout=10.0,
    countermeasure_duration=3.0,
    countermeasure_type="pursuit",
)

# Track latest detection for chase triggering
latest_detection = None
detection_lock = threading.Lock()

def on_yolo_detection(img_path):
    """Called by YoloDetector when bird detected."""
    nonlocal latest_detection
    # Parse detection center from the detector's last result
    if detector.detections_total > 0:
        # Get last detection info from detector internals
        with detection_lock:
            latest_detection = DetectionTarget(
                center_x=320, center_y=240,  # from detector's last bbox center
                frame_width=640, frame_height=480,
            )
    print(f"DETECTION_IMAGE:{img_path}", flush=True)

detector._on_detection = on_yolo_detection

# Main flight loop (replaces static hover):
while flight_active:
    if chase_ctrl.state == ChaseState.IDLE and latest_detection is not None:
        # Bird detected! Start chase
        target = latest_detection
        latest_detection = None
        chase_ctrl.start(target)
        print(f"CHASE_START:{chase_ctrl.countermeasure_type}", flush=True)

    if chase_ctrl.state != ChaseState.IDLE and not chase_ctrl.is_complete:
        # In chase mode — let ChaseController drive
        with detection_lock:
            current = latest_detection
            latest_detection = None
        cmd = chase_ctrl.update(current)
        await drone.offboard.set_velocity_body(
            VelocityBodyYawspeed(cmd.forward_m_s, cmd.right_m_s, 0.0, cmd.yawspeed_deg_s)
        )

        if chase_ctrl.is_complete:
            print(f"CHASE_END:{chase_ctrl.outcome}", flush=True)
            chase_ctrl.state = ChaseState.IDLE
            # Resume patrol...
    else:
        # Normal patrol (wall follow or hover)
        # ... existing patrol code ...

    await asyncio.sleep(0.05)
```

### 3. ChaseEventService Integration

**File**: `webapp/backend/services/chase_event_service.py` (from Phase 1)

Parse CHASE_START: and CHASE_END: lines from subprocess stdout (in DroneService._monitor):

```python
# In DroneService._monitor() or DetectionService._monitor():
elif line.startswith("CHASE_START:"):
    measure_type = line.split(":", 1)[1]
    chase = self.chase_service.start_chase(
        flight_id=self._flight_id,
        detection_image_id=None,  # could parse from detection
        counter_measure_type=measure_type,
    )
    self._active_chase_id = chase.id

elif line.startswith("CHASE_END:"):
    outcome = line.split(":", 1)[1]
    if self._active_chase_id:
        self.chase_service.end_chase(self._active_chase_id, outcome)
        self._active_chase_id = None
```

### 4. Stdout Protocol Summary

Complete protocol for chase-enabled flight scripts:
```
DETECTION_IMAGE:/path/to/detection_0001.png     — YOLO found a bird
CHASE_START:pursuit                              — chase sequence started
CHASE_END:dispersed                              — chase complete (or "lost", "aborted")
TELEMETRY:{"battery":85,"distance":12,"detections":3}  — periodic telemetry
VIDEO_PATH:/path/to/flight_camera.mp4            — video built after landing
```

---

## Simulation Setup

**World**: `drone_garage.sdf` — has `pigeon_billboard` model at 5m in front of spawn

**Launch**:
```bash
source scripts/shell/env.sh
./scripts/shell/launch.sh drone_garage
# In pxh>: commander set_gps_global_origin 0 0 0
```

**What should happen**:
1. Drone takes off, starts patrol/hover
2. Camera sees pigeon_billboard
3. YOLO detects "pigeon" -> prints DETECTION_IMAGE
4. Chase triggers -> prints CHASE_START:pursuit
5. Drone yaws toward billboard, flies forward
6. Counter-measure: oscillating yaw at target
7. Monitor: bird is a static billboard, so it stays visible -> re-engage or timeout
8. Chase ends -> prints CHASE_END:lost (billboard never leaves)
9. Drone resumes patrol

**Realistic test**: Billboard never disperses. To test "dispersed" outcome, the chase needs to timeout or the billboard needs to be outside detection range. For demo purposes, set pursuit_timeout short (5s) so the chase cycles quickly.

---

## Verification

### Unit test (no sim needed)
```python
from scarecrow.chase.chase_controller import ChaseController, DetectionTarget, ChaseState

def test_pursuit_yaws_toward_target():
    ctrl = ChaseController()
    target = DetectionTarget(center_x=500, center_y=240)  # right of center
    ctrl.start(target)
    cmd = ctrl.update(target)
    assert cmd.yawspeed_deg_s > 0  # yaw right
    assert cmd.forward_m_s > 0     # moving forward

def test_chase_completes_when_bird_lost():
    ctrl = ChaseController(pursuit_timeout=0.1)
    target = DetectionTarget(center_x=320, center_y=240)
    ctrl.start(target)
    import time; time.sleep(0.2)
    cmd = ctrl.update(None)  # bird gone
    assert ctrl.is_complete
    assert ctrl.outcome == "lost"

def test_countermeasure_oscillates_yaw():
    ctrl = ChaseController(countermeasure_duration=1.0)
    target = DetectionTarget(center_x=320, center_y=240)  # centered = reached
    ctrl.start(target)
    ctrl.update(target)  # should transition to countermeasure
    cmd = ctrl.update(target)
    assert abs(cmd.yawspeed_deg_s) > 0  # oscillating
```

### Full sim test
```bash
source .venv-mavsdk/bin/activate
python3 scripts/flight/demo_flight.py 2>&1 | grep -E "CHASE_|DETECTION_"

# Expected output:
# DETECTION_IMAGE:/path/to/detection_0001.png
# CHASE_START:pursuit
# CHASE_END:lost   (billboard doesn't move)
```

### DB verification
```bash
sqlite3 webapp/backend/database/scarecrow.db "SELECT * FROM chase_events"
# Should show chase records with flight_id, counter_measure_type, outcome
```

### Webapp verification
```bash
# Start webapp, run detection flight
# In Flight History: click a flight with chase events
# Chase Event Log should show: start time, end time, type, outcome
```
