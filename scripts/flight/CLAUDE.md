# flight

Python scripts for autonomous flight missions. Run with `.venv` activated. Each script is self-contained: connects to MAVSDK, verifies sensors, arms, flies, and lands.

The webapp spawns these as subprocesses via DetectionService and parses their stdout for status updates. Stdout protocol lines recognized:
- `DETECTION_IMAGE:/path/to/img.png` — saved detection frame
- `TELEMETRY:{"battery":N,"distance":N,"detections":N}` — periodic state update (also carries `altitude`, `heading`, `phase` when the script has them)
- `VIDEO_PATH:/path/to/flight_camera.mp4` — video built after landing

DetectionService ALSO mines the plain human log lines for extra live readouts that no TELEMETRY field carries, and merges them into the telemetry payload the webapp shows. These are best-effort regex extractions (covered by `tests/unit/webapp/services/test_detection_log_parser.py`), so keeping the wording stable matters:
- `--- Phase N: <desc> ---` → `phase` (short uppercase label from `<desc>`)
- `... agl=X.XXm ...` → `agl` (live altitude-above-ground during climb/descent)
- `... ceiling clearance X.XXm ...` → `ceiling` (ceiling-clearance scripts)
- `Leg N complete` → `leg` (room-circuit progress; the v2 `--- Leg N/M ---` start banner is intentionally NOT matched)
- `Front:/Left:/Right:` or `front=/left=/right=/rear=/wall=` (with `m`, or `inf` = no wall) → `front`/`left`/`right`/`rear`/`wall` lidar distances
- `fwd=±X lat=±X yaw=±X` → `fwd`/`lat`/`yaw` commanded velocities
- `TARGET REACHED! Front distance: X.XXm` / `Pursuit ended: <reason>` → `target` (+ `target_dist`)
- `Wall follow stopped: <reason>` → `stop_reason`
- `FPS: X.XX` → `fps`

## Files
- `room_circuit_map.py` — Mapping flight: runs a 4-leg circuit, records lidar-based MapUnit samples, writes JSON map under `scarecrow/mapped_env/<datetime>/map.json`, emits `MAP_RESULT:`.
- `wall_follow.py` — Legacy single-leg wall-following mission using direct MAVSDK System calls.
- `wall_follow_v2.py` — Wall-follow v2: world-agnostic, uses `Drone` + `GazeboLidar` + `FrontWallDetector`, configurable side/target distance/speed/stop distance.
- `detect_pigeons.py` — Standalone YOLO detection from Gazebo camera feed without flight. Topic discovery is constrained to drone camera (`holybro_x500`) so monitoring cameras do not contaminate detection tests.
- `demo_flight_pursuit.py` — **Pigeon pursuit flight.** Extends `demo_flight_v2.py`: hovers with YOLO, then delegates target pursuit to `NavigationUnit.pursue_target()` using `TargetTracker` + `TargetPursuitConfig`. Holds at target before returning toward takeoff N/E, then performs lidar-assisted descent and video export.
- `corner_circuit.py` — Reference circuit mission: takeoff, stabilize from the nearest corner, run clockwise wall-follow legs with 90-degree turns, and land. Used as the basis for hangar circuit pursuit leg/turn behavior.
- `hangar_circuit_pursiot.py` — Hangar-lite pigeon mission: use a 2m wall-follow target, auto-set PX4 takeoff altitude from upward rangefinder ceiling clearance, run a 4-leg left-wall circuit with live-only YOLO detection, interrupt into a pre-pursuit entry planner, then reusable target pursuit. The planner can advance along the wall, slowly yaw/reacquire the target, or reject unsafe geometry before pursuit starts. On success it hovers at target distance, removes pursued targets when possible, returns to the pursuit entry, restores heading, and resumes scanning. Failed pursuits return to the entry and retry once before marking the target failed and resuming the leg. Lands with lidar hold and saves a customer-facing mission map. Image saving is limited to the wall-follow trigger plus three pursuit snapshots: start, centered, and reached.
- `ceiling_clearance_flight.py` — Upward rangefinder flight test for roofed worlds: takeoff to 2.5m AGL, lidar-stabilize, climb until the ceiling sensor reads 1.5m clearance, hover, descend until the ceiling sensor reads 2.5m clearance, hover, then lidar-assisted land. Defaults to a 60s climb timeout and logs ceiling clearance continuously during climb/hover/descent/landing.
- `sensor_check.py` — Sensor diagnostics: checks lidar scan, compass heading, optical flow status. No flight.
