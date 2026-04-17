# navigation

Navigation classes for the ADD's domain model. Wraps the lower-level controllers in `scarecrow/controllers/` into a facade, and provides the area-map recorder for UC1.

## Files
- `__init__.py` — Re-exports `NavigationUnit`, `MapUnit`, `MappingPoint`
- `navigation_unit.py` — `NavigationUnit`: async facade over controllers + MAVSDK. Methods: `wall_follow(side, target_distance, forward_speed, front_stop_distance, timeout)` (composes WallFollowController + FrontWallDetector in an async loop), `stabilize(targets, timeout)` (delegates to `scarecrow.flight.stabilization.lidar_stabilize`), `rotate(direction)` (delegates to `scarecrow.controllers.rotation.rotate_90`), `circuit(num_legs, side, target_distance)` (loops wall_follow + rotate for room perimeter). Takes a `Drone` + `LidarSource`.
- `map_unit.py` — `MapUnit`: area boundary recorder for UC1 Map Area. `start_mapping()`, `record_position(scan, north_m, east_m)` during flight, `finish_mapping()` -> `{"boundaries": JSON, "area_size": float}`. Computes axis-aligned bounding box from all sampled wall distances. Stub -- not full SLAM.
- `MappingPoint` dataclass: single recorded measurement (x, y NED position + front/rear/left/right wall distances).

## Design Decisions
- `NavigationUnit` **delegates rather than reimplements** existing controllers. The math (PD gains, SVD yaw alignment, clustering) stays in `controllers/` -- no duplication.
- `wall_follow()` is the only method with its own async loop, because the legacy `scripts/flight/wall_follow.py` was tightly coupled to its script-style orchestration and couldn't be directly reused.
- `MapUnit` computes a bounding box rather than a proper polygon -- full SLAM is out of scope for the university project.