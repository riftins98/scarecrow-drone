# flight

Python scripts for autonomous flight missions. Run with `.venv-mavsdk` activated. Each script is self-contained: connects to MAVSDK, verifies sensors, arms, flies, and lands.

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
- `hangar_circuit_pursiot.py` — Current webapp mission script. Hangar-lite pigeon mission: use a 2m wall-follow target, auto-set PX4 takeoff altitude from upward rangefinder ceiling clearance, run a 4-leg left-wall circuit with live-only YOLO detection, interrupt into reusable target pursuit, hover at target distance on success, remove pursued targets when possible, return to the pursuit entry, restore heading, and resume scanning. Start/corner stabilization locks both wall distances and target altitude before continuing. Failed pursuits return to the entry and retry once before marking the target failed and resuming the leg. Lands with lidar hold and saves a customer-facing mission map. Forces line-buffered stdout/stderr so the webapp terminal receives normal `print(...)` rows immediately.
- `sensor_check.py` — Sensor diagnostics: checks lidar scan, compass heading, optical flow status. No flight.
