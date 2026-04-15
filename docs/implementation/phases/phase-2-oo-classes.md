# Phase 2: Core OO Classes

**Dependencies**: Phase 1 (services exist to integrate with)
**Estimated size**: Large (4 new classes)

## Goal

Create the ADD's domain classes (Drone, Flight, NavigationUnit, MapUnit) that replace scattered MAVSDK calls and procedural flight scripts.

## Pre-read

Before starting, read these files:
- `scarecrow/controllers/__init__.py` -- existing controller exports
- `scarecrow/controllers/wall_follow.py` -- WallFollowController pattern
- `scarecrow/controllers/distance_stabilizer.py` -- DistanceStabilizerController pattern
- `scarecrow/controllers/rotation.py` -- rotate_90 function
- `scarecrow/flight/helpers.py` -- existing flight helpers (get_position, wait_for_altitude, wait_for_stable)
- `scarecrow/flight/stabilization.py` -- lidar_stabilize wrapper
- `scarecrow/sensors/lidar/base.py` -- LidarScan, LidarSource
- `scarecrow/sensors/camera/base.py` -- CameraSource
- `scarecrow/detection/yolo.py` -- YoloDetector
- `scripts/flight/demo_flight.py` -- main flight script (procedural orchestration to absorb)
- `scripts/flight/room_circuit.py` -- room circuit script (procedural navigation to absorb)

## Tasks

### 1. Drone Class

**File**: `scarecrow/drone.py`

Wraps `mavsdk.System` with high-level async methods. Absorbs boilerplate from flight scripts.

```python
"""High-level drone interface wrapping MAVSDK."""
from __future__ import annotations

import asyncio
from typing import Optional, Literal

from mavsdk import System
from mavsdk.offboard import VelocityBodyYawspeed

from .controllers.wall_follow import VelocityCommand


class Drone:
    """Async drone interface for both simulation and hardware.

    Args:
        system_address: MAVSDK connection string (default: udp://:14540 for sim).
        mode: "sim" or "hardware".
    """

    def __init__(
        self,
        system_address: str = "udp://:14540",
        mode: Literal["sim", "hardware"] = "sim",
    ):
        self._system = System()
        self._address = system_address
        self.mode = mode
        self._ground_z: float = 0.0

    # -- Connection --
    async def connect(self, timeout: float = 30.0) -> None: ...
    async def wait_for_health(self, timeout: float = 30.0) -> bool: ...

    # -- Basic commands --
    async def arm(self) -> None: ...
    async def takeoff(self, altitude: float = 2.5) -> None: ...
    async def land(self) -> None: ...
    async def return_home(self) -> None: ...
    async def emergency_stop(self) -> None: ...

    # -- Offboard control --
    async def start_offboard(self) -> None: ...
    async def stop_offboard(self) -> None: ...
    async def set_velocity(self, cmd: VelocityCommand) -> None: ...

    # -- Telemetry --
    async def get_position(self): ...  # reuse from flight/helpers.py
    async def get_yaw(self) -> float: ...  # reuse from controllers/rotation.py
    async def get_battery(self) -> float: ...
    @property
    def ground_z(self) -> float: ...
    @property
    def is_armed(self) -> bool: ...
    @property
    def is_in_air(self) -> bool: ...
```

**Key reuse points**:
- `connect()` -- absorb the `async for state in drone.core.connection_state()` pattern from demo_flight.py
- `get_position()` -- reuse `scarecrow.flight.helpers.get_position()` exactly
- `get_yaw()` -- reuse `scarecrow.controllers.rotation.get_yaw()` exactly
- `set_velocity()` -- wrap `VelocityCommand` -> `VelocityBodyYawspeed` conversion
- `takeoff()` -- absorb `wait_for_altitude()` + `wait_for_stable()` from helpers.py

### 2. NavigationUnit Class

**File**: `scarecrow/navigation/__init__.py` (empty)
**File**: `scarecrow/navigation/navigation_unit.py`

Facade over existing controllers. Replaces procedural code in flight scripts.

```python
"""Unified navigation interface combining all flight controllers."""
from __future__ import annotations

from ..controllers.wall_follow import WallFollowController
from ..controllers.distance_stabilizer import DistanceStabilizerController, DistanceTargets
from ..controllers.front_wall_detector import FrontWallDetector
from ..controllers.rotation import rotate_90
from ..flight.stabilization import lidar_stabilize
from ..sensors.lidar.base import LidarSource
from ..drone import Drone


class NavigationUnit:
    """High-level navigation combining wall-follow, stabilize, and rotate.

    Args:
        drone: Drone instance (must be in offboard mode).
        lidar: Active LidarSource.
    """

    def __init__(self, drone: Drone, lidar: LidarSource):
        self.drone = drone
        self.lidar = lidar

    async def wall_follow(
        self,
        side: str = "left",
        target_distance: float = 2.0,
        forward_speed: float = 0.3,
        front_stop_distance: float = 2.0,
    ) -> bool:
        """Follow a wall until front obstacle detected. Returns True if stopped normally."""
        # Create WallFollowController + FrontWallDetector, run loop
        # Reuse pattern from scripts/flight/wall_follow.py
        ...

    async def stabilize(self, targets: DistanceTargets, timeout: float = 12.0) -> bool:
        """Hold position at specified wall distances. Returns True if locked."""
        # Delegate to lidar_stabilize() from flight/stabilization.py
        return await lidar_stabilize(
            self.drone._system, self.lidar, targets, timeout=timeout
        )

    async def rotate(self, direction: str = "right") -> bool:
        """Rotate 90 degrees. Returns True if aligned."""
        # Delegate to rotate_90() from controllers/rotation.py
        return await rotate_90(self.drone._system, self.lidar, direction=direction)

    async def circuit(self, num_legs: int = 4, side: str = "left", target_distance: float = 2.0) -> bool:
        """Navigate a room perimeter (wall-follow + rotate for each leg)."""
        # Absorb pattern from scripts/flight/room_circuit.py
        for leg in range(num_legs):
            await self.wall_follow(side=side, target_distance=target_distance)
            if leg < num_legs - 1:
                await self.rotate(direction="right")
        return True
```

### 3. Flight Class (Orchestrator)

**File**: `scarecrow/flight/flight.py`

Orchestrates a complete mission. Replaces the procedural try/except/finally in demo_flight.py.

```python
"""Flight orchestrator coordinating drone, navigation, detection, and recording."""
from __future__ import annotations

import asyncio
from typing import Callable, Optional, Protocol

from ..drone import Drone
from ..navigation.navigation_unit import NavigationUnit
from ..detection.yolo import YoloDetector
from ..sensors.lidar.base import LidarSource
from ..sensors.camera.base import CameraSource


class FlightPhase(Protocol):
    """A phase of a flight mission."""
    async def execute(self, flight: "Flight") -> None: ...


class Flight:
    """Orchestrates a complete flight mission.

    Manages the lifecycle: preflight -> takeoff -> phases -> landing.
    Reports status via callback for webapp integration.

    Args:
        drone: Drone instance.
        lidar: LidarSource for navigation.
        camera: Optional CameraSource for detection.
        detector: Optional YoloDetector for bird detection.
        on_status: Optional callback(status_dict) for real-time updates.
    """

    def __init__(
        self,
        drone: Drone,
        lidar: LidarSource,
        camera: Optional[CameraSource] = None,
        detector: Optional[YoloDetector] = None,
        on_status: Optional[Callable] = None,
    ):
        self.drone = drone
        self.lidar = lidar
        self.camera = camera
        self.detector = detector
        self.nav = NavigationUnit(drone, lidar)
        self._on_status = on_status
        self.status = "idle"
        self.detections: list = []
        self.chase_events: list = []

    async def run(self, phases: list[FlightPhase], altitude: float = 2.5) -> dict:
        """Execute a full mission. Returns summary dict."""
        try:
            self.status = "preflight"
            await self.drone.connect()
            await self.drone.arm()
            await self.drone.takeoff(altitude)
            await self.drone.start_offboard()

            self.status = "in_progress"
            for phase in phases:
                await phase.execute(self)

            self.status = "landing"
            await self.drone.stop_offboard()
            await self.drone.land()
            self.status = "completed"
        except Exception as e:
            self.status = "failed"
            await self.drone.emergency_stop()
            raise
        finally:
            if self.detector:
                self.detector.stop()

        return self._summary()

    def _summary(self) -> dict: ...

    def on_bird_detected(self, detection) -> None:
        """Called by detector when bird found. Adds to detections list."""
        self.detections.append(detection)

    async def abort(self) -> None:
        """Emergency abort. Safe to call from any state."""
        self.status = "aborted"
        try:
            await self.drone.stop_offboard()
        except Exception:
            pass
        await self.drone.land()
```

### 4. MapUnit Class (Stub)

**File**: `scarecrow/navigation/map_unit.py`

Records boundary data during mapping flights. Stub implementation -- full SLAM is out of scope.

```python
"""Area mapping unit -- records boundaries during mapping flights."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import json
import math

from ..sensors.lidar.base import LidarScan


@dataclass
class MappingPoint:
    x: float  # north_m (NED)
    y: float  # east_m (NED)
    front_dist: float
    rear_dist: float
    left_dist: float
    right_dist: float


class MapUnit:
    """Records area boundaries during a mapping flight.

    Collects lidar distance measurements at each position to estimate
    room boundaries. Not full SLAM -- just boundary estimation.
    """

    def __init__(self):
        self.points: list[MappingPoint] = []
        self.active = False

    def start_mapping(self) -> None:
        self.points = []
        self.active = True

    def record_position(self, scan: LidarScan, north_m: float, east_m: float) -> None:
        """Record a measurement point."""
        if not self.active:
            return
        self.points.append(MappingPoint(
            x=north_m, y=east_m,
            front_dist=scan.front_distance(),
            rear_dist=scan.rear_distance(),
            left_dist=scan.left_distance(),
            right_dist=scan.right_distance(),
        ))

    def finish_mapping(self) -> dict:
        """Compute boundary estimate from recorded points. Returns AreaMap-like dict."""
        self.active = False
        if not self.points:
            return {"boundaries": "[]", "area_size": 0.0}

        # Simple bounding box from all positions + wall distances
        min_x = min(p.x - p.rear_dist for p in self.points)
        max_x = max(p.x + p.front_dist for p in self.points)
        min_y = min(p.y - p.left_dist for p in self.points)
        max_y = max(p.y + p.right_dist for p in self.points)

        boundaries = [
            {"x": min_x, "y": min_y},
            {"x": max_x, "y": min_y},
            {"x": max_x, "y": max_y},
            {"x": min_x, "y": max_y},
        ]
        area_size = (max_x - min_x) * (max_y - min_y)

        return {
            "boundaries": json.dumps(boundaries),
            "area_size": round(area_size, 2),
        }
```

## Verification

1. `python -c "from scarecrow.drone import Drone"` -- imports without error
2. `python -c "from scarecrow.navigation.navigation_unit import NavigationUnit"` -- imports
3. `python -c "from scarecrow.flight.flight import Flight"` -- imports
4. `python -c "from scarecrow.navigation.map_unit import MapUnit"` -- imports
5. Existing flight scripts still work unchanged (new classes don't break old code)
6. Run any existing tests: `python -m pytest tests/ -x -q`
