# Architecture

The README explains *how the drone navigates*. This explains *how the software
is put together* — what runs, what talks to what, and where to look when
something misbehaves.

## Processes

Nothing here is a monolith. A running system is five or six separate processes,
and most confusing failures are really one of them being absent, stale, or
talking to the wrong partner.

```
     browser
        │  http :8000  (UI + REST, one origin)
        ▼
  ┌──────────────┐   spawns    ┌────────────────────────┐
  │   backend    │────────────►│ launch_with_stream.sh  │
  │  (FastAPI)   │             └───────────┬────────────┘
  └──────┬───────┘                         │ spawns
         │ spawns                          ├──► px4  (SITL)  ──┐
         │                                 ├──► gz sim        │ lockstep
         ▼                                 └──► stream_camera │ + gz topics
  ┌──────────────┐                                   │        │
  │ flight script│                                   │ :8080  │
  │  (subprocess)│◄──────────────────────────────────┼────────┘
  └──────┬───────┘         gz topics (sensors)       │
         │ spawns                                    ▼
         └──► mavsdk_server ──udp :14540──► px4   browser <video>
```

**The backend never flies the drone.** It spawns a flight script as a
subprocess and reads its stdout. That is the whole coupling — which is why a
mission can be run identically from the command line with `pixi run fly` and
nothing about the webapp is required to fly.

| port | who listens | for |
|---|---|---|
| 8000 | backend | UI and REST API — one origin, no CORS |
| 8080 | `stream_camera.py` | MJPEG video |
| 14540 | PX4 SITL | MAVLink; `mavsdk_server` connects here |
| 3000 | React dev server | macOS development only |

In Docker and `pixi run webapp-prod` the backend serves the built React bundle
itself, so 3000 does not exist and the product is one port.

### Failure modes this topology creates

**A leaked process poisons the next run.** `mavsdk_server` outliving a killed
flight script squats on udp 14540, so the next flight cannot connect. PX4 is
worse: `pkill -x px4` leaves `px4-mavlink` and the `rcS` shell alive, and the
next launch fails with `Task already running` followed by a preflight error
naming the EKF — which points at the wrong thing entirely. Both are handled in
`sim_service.py`, and both are why teardown is a checklist item.

**Sensors can silently take the slow path.** Each sensor prefers an in-process
`gz.transport13` subscription and falls back to spawning `gz topic -e -n 1`
per sample if the bindings are missing. The fallback works — it is just a
fork+exec per reading, which starves the simulator. It logs nothing alarming.
Check `sensor.using_transport`.

## Layers

```
  scripts/flight/*.py        entry point: parse args, asyncio.run()
        │
  scarecrow/missions/        the mission: phases, config, reporting
        │
  scarecrow/navigation/      NavigationUnit — async facade over controllers
        │
  scarecrow/controllers/     pure computation: sensors in, velocity out
        │
  scarecrow/platform/        the seam: SensorSuite, sim or hardware
        │
  scarecrow/sensors/         drivers, one per sensor per environment
```

The rule that keeps this honest: **controllers are pure.** They take sensor
readings and return a `VelocityCommand`; they do not await, do not read the
clock, and do not know MAVSDK exists. That is why they are the most heavily
tested part of the codebase and why a control question can be answered by a
unit test instead of a flight.

The async loops that drive them live one level up, in `navigation/` and in the
`corner_stabilizer` / `point_navigator` helpers.

## The mission

`HangarCircuitPursuitMission` is a phase sequence, not a single loop. Each
phase is a method, and the leg loop's control flow is explicit in a
`LegOutcome` (`corner_reached` / `target_handled` / `circuit_complete` /
`abort`) rather than hidden in `continue` and `return` inside a long body.

```
  1  approach circuit start corner
  2  ceiling safety check           (only with --ceiling-clearance)
  3  circuit wall-follow + detection  ◄────────────┐
        │ pigeon detected                          │
        ▼                                          │
  4  pursue target      (retried up to N attempts) │
  5  return to pursuit entry                       │
  6  restore pre-pursuit heading                   │
  7  resume interrupted leg ──────────────────────►┘
        │ circuit complete
        ▼
     land, write annotated map
```

Phases 5–7 exist because a pursuit interrupts a leg partway. Without them the
drone would resume from wherever the chase ended, having lost its place on the
wall.

## The webapp

```
  HTTP  →  controllers/   route + Pydantic validation
        →  services/      business logic, subprocess ownership
        →  repositories/  SQL via DTOs
        →  database/      SQLite
```

Two services are different in kind from the rest: `sim_service` and
`detection_service` own external processes and hold mutable state (a PID, a
running flag, parsed stdout). Everything else is pure orchestration over
repositories and is fully unit-tested.

### Flight-script stdout is a wire format

The backend learns what the drone is doing by **parsing the flight script's
log lines**. Some are structured (`DETECTION_IMAGE:`, `TELEMETRY:{json}`,
`VIDEO_PATH:`, `MAP_RESULT:`), but most live telemetry is mined from ordinary
human-readable output with regexes — altitude, leg number, lidar distances,
commanded velocities, pursuit outcome.

This means **reformatting a status line silently removes a gauge from the
operator's screen** and raises no error anywhere. The wording is deliberately
concentrated in `reporting.py` and `scarecrow/util/formatting.py` for that
reason, and the parser is unit-tested against the exact strings. See
`scripts/flight/CLAUDE.md` for the full list.

## Where documentation lives

Per-directory `CLAUDE.md` files carry the local detail and, more importantly,
the reasoning — why a value is what it is, what was tried and failed, which
apparently-arbitrary choice is load-bearing. Read the one for the area you are
changing. This file is only the map between them.
