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
| Phase | File | Status | Summary |
|-------|------|--------|---------|
| 0 | `phases/phase-0-database.md` | **DONE** | SQLite migrations: area_maps, telemetry, chase_events |
| 1 | `phases/phase-1-backend-architecture.md` | **DONE** | DTOs, Repositories, Services, Controllers (40 API routes) |
| 2 | `phases/phase-2-oo-classes.md` | **DONE** | Drone, Flight, NavigationUnit, MapUnit + demo_flight_v2.py |

### Drone Use Cases (sim required, deep detailed docs)
| Phase | File | Status | Summary |
|-------|------|--------|---------|
| 3 | `phases/phase-3-uc1-map-area.md` | Not started | Mapping flight, MapUnit integration, area_maps CRUD |
| 4 | `phases/phase-4-uc4-uc3-detection-video.md` | **Partly done via Phase 2** | Detection + video works end-to-end; only patrol-over-area-map needs Phase 3 |
| 5 | `phases/phase-5-uc5-chase-birds.md` | Not started | ChaseController, pursuit, counter-measures, state machine |
| 6 | `phases/phase-6-uc7-abort-mission.md` | Not started | SIGTERM handling, emergency landing, abort API |

### Polish (no sim needed)
| Phase | File | Status | Summary |
|-------|------|--------|---------|
| 7 | `phases/phase-7-frontend.md` | Not started | New pages, telemetry, routing, abort button |
| 8 | `phases/phase-8-testing.md` | **UT-01..21 + IT done via Phase 0-2 (217 tests)**; IT-03..05 need Phases 3-6 | 21 unit + 5 integration tests |
| 9 | `phases/phase-9-documentation.md` | Not started | CLAUDE.md, README, ADD coverage matrix |

## Specs (apply to ALL phases)

| File | What it governs |
|------|----------------|
| `specs/workflow.md` | Step-by-step implementation process |
| `specs/testing.md` | Test fixtures, mocking, conftest.py, verification |
| `specs/security.md` | SQL injection, path traversal, subprocess safety |
| `specs/code-style.md` | Naming, imports, type hints, commit rules |
| `specs/add-gap-analysis.md` | Full ADD vs current state comparison |

## Current State Summary

**Working end-to-end (Phases 0-2 complete)**:
- PX4+Gazebo sim with optical-flow navigation
- YOLO detection wired to webapp (detection images + count visible in UI)
- Layered FastAPI backend: Controllers -> Services -> Repositories -> DTOs -> SQLite
- 40 API routes (all ADD A.1-A.7 endpoints exposed)
- 6 DB tables with idempotent migrations
- Drone / Flight / NavigationUnit / MapUnit OO classes
- `demo_flight_v2.py` uses the OO layer; webapp spawns it as subprocess
- Video recording via PNG+ffmpeg workaround
- 217 automated tests (109 unit + 62 integration + 46 Phase 2 additions), ~2.5s run time

**Still missing**:
- UC1 Map Area flight script (MapUnit class exists but no mapping flight wired)
- UC5 Chase Birds (ChaseController does not exist)
- UC7 Abort Mission (SIGTERM handler + webapp abort button)
- Frontend expansion (Area Mapping page, Telemetry panel, Detection Gallery, Chase Event Log, abort button)
- Documentation polish

## Key Constraints (from project history)

- Camera frame parsing MUST happen after flight, not during (destabilizes drone)
- Optical flow needs 2.5m+ altitude for good feature tracking
- Never param set EKF2 at runtime (resets estimator, breaks optical flow)
- Stock x500_flow airframe defaults work — only disable GPS
- GStreamer broken on Mac — use PNG+ffmpeg workaround for video
- Indoor room world: drone crashes after ~4s (wall drift). Use drone_garage for testing.
