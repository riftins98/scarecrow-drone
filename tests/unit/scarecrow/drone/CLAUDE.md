# drone (unit tests)

Tests for `scarecrow/drone.py` with a mocked `mavsdk.System`.

## Files
- `__init__.py` — Package marker (empty).
- `test_drone.py` — Drone lifecycle: connect, arm (with retries + already-armed recovery), disarm (with kill fallback), takeoff split, verify_gps_denied_params.
