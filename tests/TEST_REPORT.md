# Test Report Summary

## Overview
This document summarizes the automated and manual testing layers for the Scarecrow drone system based on the test repository structure and test suite documentation.

## Scope
The test suite is organized into three layers to balance speed, coverage, and real-world validation constraints for drone and simulation workflows.

### Layer 1: Unit Tests (Automated, Fast)
- Focus: pure computation and deterministic logic (controllers, algorithms, repositories, services, DTOs).
- Mocking: external dependencies such as MAVSDK, YOLO, and Gazebo subprocesses are mocked.
- Database: in-memory SQLite via the `repo_db` fixture.
- Expected runtime: under 2 seconds for the full unit suite.
- Coverage target: 90%+ for unit-testable code.

### Layer 2: Integration Tests (Automated, Fast)
- Focus: full HTTP request to controller to service to repository to DB flow.
- Tooling: FastAPI TestClient via `httpx.AsyncClient`.
- Mocking: subprocess spawning only (SimService.launch, DetectionService.start). Service logic runs real code.
- Database: in-memory SQLite with migrations applied.
- Expected runtime: under 5 seconds.
- Coverage target: 100% of controller routes and service orchestration logic.

### Layer 3: Manual Simulation Verification (Human, Slow)
- Focus: real drone behavior inside Gazebo (takeoff, wall-following, detection, landing).
- Not automated due to: slow startup, flakiness, and GPU/display requirements.
- Checklist: See `docs/implementation/MANUAL_SIM_CHECKLIST.md`.

#### Hangar Circuit Pursuit Manual Testing (`hangar_circuit_pursiot.py`)
This script represents the most complex live-flight scenario and is tested manually to verify:
- **Launch Normalization:** Drone correctly aligns and normalizes its launch pose to the expected start corner using lidar.
- **Flight Stabilization:** Maintains stable altitude and follows walls smoothly across the broader hangar circuit geometry.
- **Dynamic Deterrence:** Actively processes live YOLO frames, pausing the patrol circuit to transition seamlessly into target pursuit mode upon pigeon detection.
- **Mapping & Telemetry:** Continuously logs valid Map events (e.g. `MAP_STATUS:leg_X`) and records the live route path for backend processing without interrupting the flight logic.
- **State Recovery:** Accurately returns to the original route or a stable state after the chase phase completes.

## What Is Intentionally Not Automated
These areas are validated primarily via manual simulation runs:
- PX4 process spawning and lifecycle management.
- Detection service subprocess management and stdout parsing in live sim.
- Gazebo-backed sensor integrations (lidar, camera).
- MAVSDK-dependent flight helper logic and stabilization.
- Async controller logic requiring a live drone connection.

## Test Suite Structure

### Unit Tests
- `tests/unit/scarecrow/controllers/`
  - WallFollow, CornerApproach, DistanceStabilizer, FrontWallDetector, TargetPursuit.
- `tests/unit/scarecrow/sensors/`
  - LidarScan, GazeboLidar topic discovery, rangefinder parsing, gz_utils helpers.
- `tests/unit/scarecrow/detection/`
  - YoloDetector (rate limiting, callback, preload_async), TargetTracker.
- `tests/unit/scarecrow/navigation/`
  - NavigationUnit, MapUnit.
- `tests/unit/scarecrow/flight/`
  - Flight orchestrator.
- `tests/unit/scarecrow/drone/`
  - Drone class with mocked MAVSDK System.
- `tests/unit/scripts/flight/`
  - Script-level orchestration helpers.
- `tests/unit/webapp/repositories/`
  - Repository classes (AreaMap, ChaseEvent, DetectionImage, Flight, Telemetry).
- `tests/unit/webapp/services/`
  - Services and targeted helpers (log parser, process cleanup, PX4 console, spawn validation).

### Integration Tests
- `tests/integration/`
  - API flow tests: area map, chase, connection, detection, drone, flight, lifecycle, health, sim, static.

## Running Tests
From repository root:

```bash
pytest
pytest tests/unit/
pytest tests/integration/
pytest tests/unit/test_wall_follow.py -v
pytest -k "test_create"
pytest --cov=webapp/backend --cov=scarecrow
```

## Key Fixtures
- `repo_db`: wraps the SQLite connection so repository code calling `conn.close()` does not tear down shared test state between calls.
- `in_memory_db`: raw in-memory SQLite connection for low-level testing.
- `mock_lidar_scan`: LidarScan factory for unit tests.

## Notes
- Coverage statistics should be interpreted as "trusted by manual sim" for parts that are intentionally excluded from automation.
- Integration tests mock only subprocess spawning to keep behavior realistic without costly Gazebo startup.
