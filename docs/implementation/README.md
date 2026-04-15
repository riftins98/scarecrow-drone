# Scarecrow Drone — Implementation Guide

Complete guide to close all ADD gaps. Each phase is a self-contained document that can be executed in a fresh Claude session.

## How to Use

1. Open a new Claude Code session
2. Say: "Read `docs/implementation/README.md` and the specs in `docs/implementation/specs/`, then execute Phase N from `docs/implementation/phases/`"
3. Claude reads the phase file + relevant specs and implements

## Phase Order & Dependencies

```
Phase 0 (DB Migrations) ──── no dependencies, start here
   |
   v
Phase 1 (Backend Architecture) ──── depends on Phase 0
   |
   v
Phase 2 (OO Classes) ──── depends on Phase 1
   |
   +──────────────────────────────────────────────┐
   v                                              v
Phase 3 (UC1: Map Area) ──── drone + sim     Phase 7 (Frontend) ──── no sim
   |
   v
Phase 4 (UC4+UC3: Detection + Video) ──── drone + sim
   |
   v
Phase 5 (UC5: Chase Birds) ──── drone + sim
   |
   v
Phase 6 (UC7: Abort Mission) ──── drone + sim
   |
   v
Phase 8 (Testing) ──── UT-01..11 can start anytime, rest after Phase 6
   |
   v
Phase 9 (Documentation) ──── last
```

## Phases

### Infrastructure (no sim needed)
| Phase | File | Summary | Size |
|-------|------|---------|------|
| 0 | `phases/phase-0-database.md` | SQLite migrations: area_maps, telemetry, chase_events | Small |
| 1 | `phases/phase-1-backend-architecture.md` | DTOs, Repositories, Services, Controllers | Large |
| 2 | `phases/phase-2-oo-classes.md` | Drone, Flight, NavigationUnit, MapUnit classes | Large |

### Drone Use Cases (sim required, deep detailed docs)
| Phase | File | Summary | Size |
|-------|------|---------|------|
| 3 | `phases/phase-3-uc1-map-area.md` | Mapping flight, MapUnit, area_maps CRUD | Medium |
| 4 | `phases/phase-4-uc4-uc3-detection-video.md` | Patrol detection, YOLO, video recording, telemetry | Medium |
| 5 | `phases/phase-5-uc5-chase-birds.md` | ChaseController, pursuit, counter-measures, state machine | Large |
| 6 | `phases/phase-6-uc7-abort-mission.md` | SIGTERM handling, emergency landing, abort API | Small |

### Polish (no sim needed)
| Phase | File | Summary | Size |
|-------|------|---------|------|
| 7 | `phases/phase-7-frontend.md` | New pages, telemetry, routing, abort button | Medium |
| 8 | `phases/phase-8-testing.md` | 21 unit + 5 integration tests | Large |
| 9 | `phases/phase-9-documentation.md` | CLAUDE.md, README, ADD coverage matrix | Small |

## Specs (apply to ALL phases)

| File | What it governs |
|------|----------------|
| `specs/workflow.md` | Step-by-step implementation process |
| `specs/testing.md` | Test fixtures, mocking, conftest.py, verification |
| `specs/security.md` | SQL injection, path traversal, subprocess safety |
| `specs/code-style.md` | Naming, imports, type hints, commit rules |
| `specs/add-gap-analysis.md` | Full ADD vs current state comparison |

## Current State Summary

**Working**: PX4+Gazebo sim, YOLO detection, wall-follow/stabilize/rotate controllers, lidar+camera sensors, flight scripts, basic webapp (flat FastAPI + React)

**Missing**: Layered backend, area mapping, chase birds, abort mission, telemetry, 3 DB tables, all tests, frontend pages

## Key Constraints (from project history)

- Camera frame parsing MUST happen after flight, not during (destabilizes drone)
- Optical flow needs 2.5m+ altitude for good feature tracking
- Never param set EKF2 at runtime (resets estimator, breaks optical flow)
- Stock x500_flow airframe defaults work — only disable GPS
- GStreamer broken on Mac — use PNG+ffmpeg workaround for video
- Indoor room world: drone crashes after ~4s (wall drift). Use drone_garage for testing.
