# Phase 8: Testing

**Dependencies**: UT-01..11 can start anytime. Rest needs Phases 1-6.
**Estimated size**: Large (26 tests)
**Simulation required**: No (all tests use mocks)

## Goal

Implement all 21 unit tests and 5 integration tests from ADD Sections 5.4 and 7.

## Pre-read

- `docs/implementation/specs/testing.md` — fixtures, mocking, patterns, conftest.py template

## Tasks

Full test list, code examples, and conftest.py are in `phase-5-testing.md` (the original detailed spec). That file was renamed but the content applies here. Key points:

### Batch 1: Existing controllers (start immediately)
- `tests/unit/test_wall_follow.py` (UT-01..03)
- `tests/unit/test_distance_stabilizer.py` (UT-04..05)
- `tests/unit/test_front_wall_detector.py` (UT-06..07)
- `tests/unit/test_lidar_scan.py` (UT-08..09)
- `tests/unit/test_yolo_detector.py` (UT-10..11)

### Batch 2: New backend layers (after Phase 1)
- `tests/unit/test_flight_repository.py` (UT-12)
- `tests/unit/test_area_map_repository.py` (UT-13)
- `tests/unit/test_telemetry_repository.py` (UT-14)
- `tests/unit/test_chase_event_repository.py` (UT-15)
- `tests/unit/test_flight_service.py` (UT-16)
- `tests/unit/test_drone_service.py` (UT-17)
- `tests/unit/test_area_map_service.py` (UT-18)

### Batch 3: New drone classes (after Phases 2-6)
- `tests/unit/test_chase_controller.py` (UT-19)
- `tests/unit/test_navigation_unit.py` (UT-20)
- `tests/unit/test_drone.py` (UT-21)

### Integration tests (after all phases)
- `tests/integration/test_flight_lifecycle.py` (IT-01)
- `tests/integration/test_area_map_api.py` (IT-02)
- `tests/integration/test_detection_session.py` (IT-03)
- `tests/integration/test_chase_flow.py` (IT-04)
- `tests/integration/test_telemetry_api.py` (IT-05)

## Verification
```bash
python -m pytest tests/ -x -q -v
# All 26 tests pass with zero failures
```
