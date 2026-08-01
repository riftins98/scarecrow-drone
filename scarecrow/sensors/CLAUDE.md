# sensors

Sensor interface abstractions for sim and hardware. Each sensor type has a base ABC and driver implementations for Gazebo (sim) and real hardware.

## Subdirectories
- `lidar/` — 2D lidar: LidarScan data class with geometry methods (distances, SVD wall alignment), GazeboLidar and RPLidar drivers (see `lidar/CLAUDE.md`)
- `camera/` — Camera abstractions: CameraFrame, CameraSource ABC, GazeboCamera driver (see `camera/CLAUDE.md`)
- `rangefinder/` — Single-ray rangefinder (e.g. upward ceiling clearance sensor): GazeboRangefinder driver (see `rangefinder/CLAUDE.md`)

## Files
- `__init__.py` — Re-exports single-ray rangefinder support (`GazeboRangefinder`, `RangefinderReading`) from the `rangefinder/` subpackage.
- `gz_transport.py` — **In-process Gazebo subscriptions.** `GzSubscription`
  wraps a `gz.transport13` Node; `transport_available()` reports whether the
  bindings are importable; `apply_gz_env()` exports `GZ_PARTITION`/`GZ_IP` into
  the process (a Node reads them at construction, unlike the CLI which took
  them per subprocess — miss this and the subscription silently finds no
  publisher). Every Gazebo sensor prefers this and falls back to the old
  `gz topic -e -n 1` polling when the bindings are missing (Raspberry Pi, or a
  delivery image without `python3-gz-transport13`). `sensor.using_transport`
  says which path is live.

  **Why**: the CLI path is a fork+exec *per sample, per thread*, in a spin
  loop. That cost is paid on every scan and every frame, so it scales with
  sensor rate and it competes with `gz sim` for the same cores — the simulator
  was starved rather than expensive. It also capped the lidar read rate below
  what the control loop asked for, which is the failure mode to watch for: a
  host without the bindings falls back to this path silently. Check
  `sensor.using_transport` if rates look low.
- `gz_entities.py` — Gazebo CLI/SDF entity helpers for discovering world/model names, parsing live model poses, mapping PX4 local XY into Gazebo world XY, and removing pursued target models from running worlds.
- `gz_utils.py` — Gazebo CLI helpers: `get_gz_env()` auto-detects env/partition; `prefetch_gz_env_async()` + `GzPrefetchResult` runs env detection + `gz topic -l` in a background thread so flight scripts can overlap ~2s of Gazebo setup with MAVSDK handshake


## Hardware drivers for the real drone
Each simulated sensor has a hardware counterpart with an identical interface,
so `scarecrow.platform` can swap them without the mission noticing:

| sensor | simulation | hardware |
|---|---|---|
| 2D lidar (RPLidar A1M8) | `lidar/gazebo.py` | `lidar/rplidar.py` |
| Up rangefinder (TF-Luna) | `rangefinder/gazebo.py` | `rangefinder/tfluna.py` |
| Camera (Pi Camera 3) | `camera/gazebo.py` | `camera/picamera.py` |
| Optical flow (MTF-01) | wired into PX4 | wired into PX4 |

Optical flow and the downward rangefinder feed PX4's EKF directly and are never
read by this package — true in both environments, so nothing changes.

- `rangefinder/base.py` — `RangefinderSource` / `RangefinderReading`. This
  interface was missing entirely; `GazeboRangefinder` was imported by name, so
  a hardware driver had nothing to implement against.
- `rangefinder/tfluna.py` — TF-Luna over UART (`/dev/serial0`, 115200). 9-byte
  frames, little-endian centimetres, checksum-validated. Rejects saturation
  (65535cm = no return) and low-strength returns. `_parse_frame` is pure and
  unit-tested: this sensor sets the flight altitude, so a byte-order slip flies
  the drone into a roof.
- `camera/picamera.py` — Pi Camera Module 3 via picamera2, same `on_frame`
  contract as `GazeboCamera`. Converts RGB→BGR at the source, because every
  consumer expects BGR and getting it wrong is silent — accuracy drops with
  nothing logged. Needs `sudo apt install python3-picamera2` and a venv created
  with `--system-site-packages`.
- `lidar/validation.py` — Shared reading validation (`valid_distance`,
  `scan_valid_for_map`, `nearest_start_side`, `current_landing_targets`).
