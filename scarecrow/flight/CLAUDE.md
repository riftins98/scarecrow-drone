# flight

Async MAVSDK flight helpers and the `Flight` orchestrator.

## Files
- `__init__.py` — Package marker only. **Does NOT re-export `Flight`** because importing it would trigger a circular import (`scarecrow.flight.flight` -> `scarecrow.drone` -> `scarecrow.flight.helpers`). Import it directly: `from scarecrow.flight.flight import Flight`.
- `helpers.py` — Standalone async helpers used by legacy scripts and the Drone class: `get_position(drone)`, `wait_for_altitude(drone, target_alt, ground_z, timeout)`, `wait_for_stable(drone, ground_z, tolerance, stable_secs, timeout)`, `log_position(drone, phase, ground_z)`. Take a raw `mavsdk.System` (not a Drone wrapper) so they work from any level.
- `stabilization.py` — `lidar_stabilize(drone, lidar, targets, label, timeout)`: async wrapper that creates a DistanceStabilizerController and drives MAVSDK offboard velocity until all wall targets are within tolerance or timeout. Takes a raw `mavsdk.System`.
- `flight.py` — `Flight` orchestrator class (OPTIONAL). Lifecycle scaffold: `run(mission_func, altitude)` handles connect -> wait_for_health -> set_ekf_origin -> takeoff -> start_offboard -> **user mission body** -> stop_offboard -> land. Includes on_status callback and abort(). The existing flight scripts (`demo_flight.py`, `demo_flight_v2.py`, `room_circuit.py`) do NOT use it -- they keep their proven procedural structure. Flight is for NEW missions that want a reusable lifecycle.

## Usage Pattern (for new missions using Flight)
```python
from scarecrow.drone import Drone
from scarecrow.flight.flight import Flight
from scarecrow.sensors.lidar.gazebo import GazeboLidar

async def my_mission(flight):
    await flight.nav.wall_follow(side="left")
    await flight.nav.rotate()

drone = Drone()
lidar = GazeboLidar()
flight = Flight(drone, lidar, on_status=print)
await flight.run(my_mission, altitude=2.5)
```