# missions

Complete flights. A mission owns sensor bring-up, takeoff, the phase sequence,
landing and map output; everything under `controllers/`, `sensors/` and
`navigation/` is a component it composes.

This layer exists so `scripts/flight/*.py` can be argument parsing plus an
`asyncio.run()` call. **Anything runnable, testable or reusable belongs here,
not in a script.** `hangar_circuit_pursuit.py` was 2247 lines with a 1147-line
`run()`; it is now 66 lines of entry point.

## Subdirectories
- `hangar_circuit/` — Hangar circuit pursuit mission (see below)

## hangar_circuit/

Wall-follows a hangar circuit watching for a pigeon; on a confident detection
it plans an approach geometry from the image, yaws onto the target, pursues to
a set distance, removes it from the world, returns to exactly where it broke
off, and resumes the leg.

- `config.py` — `HangarCircuitConfig`: every tunable in one dataclass (mission
  shape, altitude, the two YOLO thresholds, pursuit, entry planner, wall
  follow, rotation, mapping, output). Previously ~40 module constants that
  could not be overridden without editing the file.
- `cli.py` — argparse parser + `config_from_args`. Lives here because the
  webapp introspects it: `script_metadata.py` runs the script with `--help` and
  parses the output to build the pre-flight form, so flags, types and help text
  are a **UI contract**.
- `mission.py` — `HangarCircuitPursuitMission`, one method per phase, plus
  `LegOutcome` (corner_reached / target_handled / circuit_complete / abort)
  which makes the leg loop's control flow explicit instead of relying on
  `continue`/`return` inside a 1100-line body.
- `reporting.py` — `WallFollowReporter`, `PursuitReporter`, `LandingReporter`,
  `report_search_status`, `report_planner_decision`. Formerly nested closures
  capturing mission state via `nonlocal`.

### Phases
1. Approach circuit start corner (normalises a right-hand start by rotating)
2. Ceiling safety check (only when `--ceiling-clearance` is given)
3. Circuit wall-follow with detection — the leg loop
4. Pursue target (retried up to `max_pursuit_attempts`)
5. Return to pursuit entry
6. Restore pre-pursuit heading
7. Resume the interrupted leg

## Log wording is a wire format
The webapp parses flight-script stdout with regexes to drive the live
telemetry rail — see `webapp/backend/services/detection_service.py::_parse_log_extras`
and `scripts/flight/CLAUDE.md` for the full list. Reformatting a status line
silently removes a gauge from the operator's screen and raises no error
anywhere. Status wording lives in `reporting.py` and
`scarecrow/util/formatting.py` for exactly this reason.
