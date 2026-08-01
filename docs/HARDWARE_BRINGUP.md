# Hardware Bring-Up

Taking this from the simulator to the real aircraft.

**Nothing in this document has been done.** The hardware path is written and
unit-tested; no part of it has read a real sensor or flown. Treat every section
as a plan, not a report.

## What already transfers

The mission does not know it is in a simulator. `scarecrow/platform/` is the
seam: mission code asks for a `SensorSuite` and gets either
`GazeboSensorSuite` or `HardwareSensorSuite`, both satisfying the same
interface. `sensor_suite_for("auto")` picks by reading
`/proc/device-tree/model`, and returns `"hardware"` only on positive evidence
of a Raspberry Pi — anything ambiguous stays simulation, because that path does
not drive real motors. Override with `SCARECROW_PLATFORM` or `--platform`.

A regression test asserts `mission.py` never imports Gazebo again. If it fails,
the "install it on the Pi" property has quietly been lost.

The connection address is the only other difference:

```python
SYSTEM_ADDRESS = "udp://:14540"                    # simulation
SYSTEM_ADDRESS = "serial:///dev/ttyACM0:921600"    # companion → Pixhawk
```

Simulated sensor rates were deliberately matched to the real parts, so a
timing assumption that breaks on hardware should break in simulation first.
That is a design intent, not a guarantee.

## What does not transfer

**World services.** Knowing the drone's true world pose, and removing a target
from the world, are things only a simulator can do. `HardwareSensorSuite`
pairs with `NoWorldServices`, which reports these unsupported rather than
faking them. `TargetRemovalOutcome.supported` distinguishes "nothing to remove
here, by design" from "removal was attempted and failed" — only the second is
a fault. On a real drone a reached pigeon disperses on its own; that is the
entire point of the project.

**Position ground truth.** In simulation you can always ask Gazebo where the
drone really is. On hardware there is no such oracle — the lidar is the only
position reference, and a lidar fault looks exactly like a control fault.

## Hardware

| Sensor | Part | Interface | Default |
|---|---|---|---|
| 2D lidar | RPLidar A1M8 | USB serial | `/dev/ttyUSB0` |
| Up rangefinder | TF-Luna | UART | `/dev/serial0` |
| Forward camera | Pi Camera 3 | CSI (picamera2) | — |
| Optical flow | MTF-01 | wired to Pixhawk | — |
| Down rangefinder | TF-Luna | wired to Pixhawk | — |

Optical flow and the downward rangefinder feed PX4's EKF directly and are never
read by this package, in either environment. Nothing about them changes here.

`camera/picamera.py` needs `sudo apt install python3-picamera2`, and a venv
created with `--system-site-packages` — picamera2 is an apt package and a
sealed venv cannot see it.

## Order of bring-up

Do these one at a time, on the ground, with props off until the last step. Each
step should fail loudly on its own rather than during a flight.

**1. Install the package.**

```bash
pip install -e ".[sim,hardware]"
```

`torch` and `ultralytics` come with the `sim` extra and are large; expect this
to be the slow step on a Pi.

**2. Each sensor alone, against a tape measure.** This is the step worth being
slow about. `pixi run sensors` has a simulator equivalent; on hardware, read
each driver directly and compare to a measured distance.

- **Lidar**: a full 1440-sample scan, and `front_distance()` matching a wall
  you measured. The hardware driver resamples variable-count scans to the fixed
  1440 the simulation produces, so geometry helpers mean the same thing — but
  verify the *orientation*, because a rotated mount is silent and turns
  wall-following into wall-finding.
- **TF-Luna**: distance to a ceiling you measured. This sensor sets flight
  altitude. Its frame parser is unit-tested precisely because a byte-order
  slip flies the drone into a roof — but the test proves the parsing, not the
  wiring.
- **Camera**: one frame, and confirm it is **BGR**. `picamera.py` converts at
  the source because every consumer expects BGR; getting it wrong is silent,
  and detection accuracy simply drops with nothing logged.

**3. PX4 configuration.** The airframe under `airframes/` disables GPS and
enables optical flow. Confirm on the real autopilot:

```
EKF2_GPS_CTRL = 0     GPS off
SYS_HAS_GPS   = 0     GPS hardware off
EKF2_OF_CTRL  = 1     optical flow feeding the estimator
EKF2_RNG_CTRL         rangefinder height fusion
EKF2_OF_POS_X/Y/Z     flow sensor offset from centre of mass
EKF2_RNG_POS_X/Y/Z    rangefinder offset
```

The offsets matter more on hardware than in simulation, where the models place
sensors exactly. Measure them.

**Never `param set` an EKF2 value at runtime.** It resets the estimator and
breaks optical flow — in flight this is a crash.

**4. Hover.** Optical flow needs texture on the floor and roughly 2.5 m of
altitude for good feature tracking. A bare polished floor is the worst case; if
hold is poor, look at the floor before the gains.

**5. One wall-follow leg**, then a single corner, then the full circuit.

## Expect the corner behaviour to be worse

After a 90-degree rotation, PX4's velocity estimate disagrees with the lidar
for several seconds, because rotational motion contaminates optical flow's
translational estimate. The drone flies to a velocity it only believes it is
achieving.

The mission handles this by **holding still after each turn before correcting
position** — patience, not control. Gain tuning, damping and lidar alignment
were all tried in simulation and all failed, because the measurement was never
the problem.

Real optical flow is noisier than simulated, so the recovery is unlikely to be
*shorter* on hardware. Budget for a longer hold, and measure it: log commanded
velocity beside actual body-frame velocity through a turn and watch when they
converge. That one log line is what found the cause in simulation after three
plausible control-theory explanations turned out to be wrong.

**Any new manoeuvre that rotates and then holds position needs the same
treatment.**

The durable fix, not attempted: close the position loop on lidar-derived
velocity instead of trusting PX4's frame. That would make the mission immune
rather than patient, and it matters more on hardware than in simulation.

## Known-thin behaviours to watch

From `KNOWN_LIMITATIONS.md`, the ones most likely to bite on hardware:

- **Altitude sags ~0.6 m during pursuit** at a 5.5 m target. Thin, not broken.
- **`--r` (right-hand start) is unverified** — `stabilize_corner()` hardcodes
  the left wall, so a right-hand circuit would stabilise against the wrong one.
- **YOLO on a Pi runs on CPU.** There is no accelerator, so inference is slow.
  Rate-limit it, or accept that detection is coarse.
