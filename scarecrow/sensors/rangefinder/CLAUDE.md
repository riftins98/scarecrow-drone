# rangefinder

Single-ray rangefinder interface for narrow-beam Gazebo sensors (e.g. the upward ceiling-clearance sensor). Separate from the `lidar/` package, which expects full-circle scans.

## Files
- `__init__.py` — Exports `GazeboRangefinder`, `RangefinderReading`.
- `gazebo.py` — `RangefinderReading` (distance_m + timestamp dataclass) and `GazeboRangefinder`: polls a single-ray Gazebo scan topic via `gz topic` in a background thread. Auto-discovers the topic from a `topic_hint` (default `ceiling_rangefinder/scan`) when none is given, and rejects invalid `inf` / `nan` ranges.
