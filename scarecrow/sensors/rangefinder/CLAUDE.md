# rangefinder

Single-ray rangefinder interface for narrow-beam Gazebo sensors (e.g. the upward ceiling-clearance sensor). Separate from the `lidar/` package, which expects full-circle scans.

## Files
- `__init__.py` — Exports `GazeboRangefinder`, `RangefinderReading`.
- `base.py` — `RangefinderSource` ABC and `RangefinderReading`. Added when the hardware driver was written: `GazeboRangefinder` had been imported by name everywhere, so there was no interface for a second implementation to satisfy.
- `gazebo.py` — `GazeboRangefinder`: reads a single-ray Gazebo scan topic. Prefers an in-process `gz.transport13` subscription and falls back to `gz topic` polling in a background thread. Auto-discovers the topic from a `topic_hint` (default `ceiling_rangefinder/scan`) when none is given, and rejects invalid `inf` / `nan` ranges.
- `tfluna.py` — **Hardware driver**, TF-Luna over UART (`/dev/serial0`, 115200). 9-byte frames, little-endian centimetres, checksum-validated; rejects saturation (65535cm = no return) and low-strength returns. `_parse_frame` is pure and unit-tested because this sensor sets flight altitude — a byte-order slip flies the drone into a roof. Never run on a real drone; see `docs/KNOWN_LIMITATIONS.md`.
