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

Three scripts. Earlier versions of this file listed nine, six of which no
longer existed — they were consolidated into `scarecrow/missions/` as the
mission layer took shape (see `scarecrow/missions/CLAUDE.md`). A script here
should be an entry point; anything runnable, testable or reusable belongs in
the package.

- `hangar_circuit_pursuit.py` — **The delivery mission, and an entry point only (66 lines).** The mission itself is `scarecrow/missions/hangar_circuit/`; see its CLAUDE.md. Parses args, builds a `HangarCircuitConfig`, runs `HangarCircuitPursuitMission`. Exits via `os._exit` because the detector's and gRPC's non-daemon threads otherwise hang interpreter shutdown after a clean landing. Run it with `pixi run fly`.
- `room_circuit_map.py` — Mapping flight: runs a 4-leg circuit, records lidar-based MapUnit samples, writes JSON map under `scarecrow/mapped_env/<datetime>/map.json`, emits `MAP_RESULT:`. Unlike the mission above this one still carries its own flight logic.
- `sensor_check.py` — Sensor diagnostics, no flight: 2D lidar scan (top-down PDF plot), a saved mono-camera frame (PNG), and optical-flow quality/rate. Run it with `pixi run sensors` before trusting a flight failure — it separates "the sensor is not publishing" from "the controller is wrong."
