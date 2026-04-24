# controllers (unit tests)

Tests for `scarecrow/controllers/`. Pure computation, no async or MAVSDK.

## Files
- `__init__.py` — Package marker (empty).
- `test_wall_follow.py` — `WallFollowController` PD output + SVD yaw correction + done flag.
- `test_distance_stabilizer.py` — `DistanceStabilizerController` multi-constraint targets + stable_time gating.
- `test_front_wall_detector.py` — Clustering + temporal confirmation (confirm_cycles).
