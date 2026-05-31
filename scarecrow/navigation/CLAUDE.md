# navigation

Navigation classes for the ADD's domain model. Wraps the lower-level controllers in `scarecrow/controllers/` into a facade, and provides the area-map recorder for UC1.

## Files
- `__init__.py` — Re-exports `NavigationUnit`, `LidarHoldLandingResult`, `WallFollowResult`, `CeilingClearanceResult`, `MapUnit`, and `MappingPoint`.
- `navigation_unit.py` — `NavigationUnit`: async facade over controllers + MAVSDK. Methods include `wall_follow_until(...)` / `wall_follow(...)`, `pursue_target(tracker, config, on_status, on_search_status)` with relocalization search callbacks, `hover(duration_s)`, `land_with_lidar_hold(targets, ...)`, ceiling-clearance safety checks, `stabilize(targets, timeout)`, `rotate(direction)`, and `circuit(num_legs, side, target_distance)`. Takes a `Drone` + `LidarSource`.
- `map_unit.py` — `MapUnit`: area boundary recorder for UC1 Map Area. Records route points and front/rear/left/right lidar wall hits, writes map payloads, and renders production-friendly annotated maps with mission route phases/events by default. Pass `debug=True` to include raw wall-hit and sampled-point construction details. Computes axis-aligned wall envelopes; not full SLAM.
- `annotate_map_test.py` — CLI helper to render `map_annotated.png` from a saved `map.json` path.
- `MappingPoint` dataclass: single recorded measurement (x, y NED position + front/rear/left/right wall distances).

## Design Decisions
- `NavigationUnit` **delegates rather than reimplements** existing controllers. The math (PD gains, SVD yaw alignment, clustering, target pursuit) stays in `controllers/` -- no duplication.
- `wall_follow_until()` owns the reusable async offboard loop and accepts mission-specific stop conditions; `wall_follow()` delegates to it for the standard front-wall stop.
- `MapUnit` computes a bounding box rather than a proper polygon -- full SLAM is out of scope for the university project.
