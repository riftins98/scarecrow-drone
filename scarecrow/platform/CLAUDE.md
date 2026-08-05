# platform

The seam between mission logic and where it is flying.

**Why this exists:** the mission used to construct `GazeboLidar`,
`GazeboCamera` and `GazeboRangefinder` itself, which made the flight logic
unrunnable anywhere but simulation — putting it on the Raspberry Pi meant
editing the mission. Since the whole point of `scarecrow` is that the same code
flies the real drone, that was a hole in the design.

```python
from scarecrow.platform import sensor_suite_for

suite = sensor_suite_for("auto", repo_root=REPO_ROOT)
await HangarCircuitPursuitMission(config, sensors=suite).run()
```

## Files
- `base.py` — `SensorSuite` (lidar / ceiling rangefinder / camera + lifecycle),
  `WorldServices`, `TargetRemovalOutcome`.
- `simulation.py` — `GazeboSensorSuite`, `GazeboWorldServices`,
  `find_drone_camera_topic`. Existing behaviour, unchanged: same discovery
  order, same timeouts, same log lines.
- `hardware.py` — `HardwareSensorSuite` (RPLidar A1M8, TF-Luna, Pi Camera 3)
  and `NoWorldServices`.
- `__init__.py` — `detect_platform()` and `sensor_suite_for()`.

## Two kinds of difference

**Sensors** — same physical devices, different drivers. Fully hidden; the
mission asks for a lidar and never learns whether it came from a Gazebo topic
or a USB serial port.

**World services** — things only a simulator can do: knowing the drone's true
world pose, and deleting a bird once it is reached. These have no hardware
equivalent, so they report themselves unsupported rather than being faked.
`TargetRemovalOutcome.supported` distinguishes "nothing to remove here, by
design" from "removal was attempted and failed" — only the second is a fault.
On a real drone a reached pigeon disperses on its own; deterrence is the point.

## Platform detection
`detect_platform()` reads `/proc/device-tree/model` and returns `"hardware"`
only on positive evidence of a Raspberry Pi. Anything ambiguous is
`"simulation"`, because that path does not drive real motors. Override with
`SCARECROW_PLATFORM=simulation|hardware` or `--platform`.

## Not yet flown on hardware
The drivers are written and unit-tested (frame parsing, colour conversion,
interface parity) but **no part of the hardware path has run on a real drone.**
`tests/unit/scarecrow/platform/test_sensor_suite.py` includes a regression
guard asserting `mission.py` never imports Gazebo again — if that test fails,
the "install it on the Pi" property has silently been lost.
