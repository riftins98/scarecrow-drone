# controllers

Flight control algorithms for GPS-denied indoor navigation. All controllers are pure computation — they take sensor data in, return VelocityCommand out. No MAVSDK or async code here; the flight scripts and NavigationUnit handle the async offboard loop.

## Files
- `__init__.py` — Exports: CornerApproachController, DistanceStabilizerController, DistanceTargets, rotate_90, VelocityCommand, WallFollowController, and target-pursuit types.
- `corner_approach.py` — Pure lidar controller for safe rear-left/rear-right corner approach. Treats rear/side targets as a safe band, caps combined diagonal speed, and brakes when closing too quickly near the target distances.
- `wall_follow.py` — PD controller maintaining target distance from wall. Outputs body-frame velocity with SVD-based yaw correction. Has `done` property for front-wall stop. Configurable: side (left/right), target_distance, forward_speed, kp/kd gains.
- `target_pursuit.py` — Pure vision+lidar target pursuit controller. Consumes latest target observation plus lidar scan and outputs `VelocityCommand` with target alignment, approach, missing-target/search, timeout, and wall-safety state. Target-distance success takes priority over side-wall safety once the front lidar reaches the requested stop distance.
- `rotation.py` — Precise 90-degree rotation using compass (coarse turn to ~95 degrees overshoot) + lidar SVD wall alignment (fine-tune). Async function `rotate_90()` takes drone + lidar. Works for both left and right turns.
- `distance_stabilizer.py` — Multi-constraint hover positioning using lidar distances. Supports any combination of front/rear/left/right targets. Reports `done` when all constraints within tolerance for stable_time seconds.
- `front_wall_detector.py` — Robust front obstacle detection with DBSCAN-style clustering and temporal confirmation (confirm_cycles). Prevents false stops from off-axis obstacles or floor returns.
