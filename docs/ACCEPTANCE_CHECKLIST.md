# Acceptance Checklist — manual flight verification

`docker/verify-delivery.sh` proves the *environment* works: rendering, the
stream, GPU passthrough, one short flight. This checklist covers what only a
human watching a full mission can judge — whether the drone actually flies
well.

Run it after any change to `scarecrow/controllers/*`, `scarecrow/sensors/*`,
`scarecrow/missions/*`, `scripts/flight/*`, an airframe, or a world file. Run
it once on delivery hardware before signing off.

## Setup

**macOS:**

```bash
pixi run sim
```

**Windows / Linux:**

```bash
docker compose up
```

Both launch PX4 SITL, Gazebo and the monitoring stream. The first launch after
a build is slow because PX4 relinks; later launches are quick. `pixi run sim`
is the only supported
way in on macOS — invoking `scripts/shell/launch_with_stream.sh` from a plain
shell fails with `ERROR [init] Gazebo gz sim not found`, because the toolchain
lives in the pixi environment and not on your PATH.

The launcher sets the EKF origin itself. If you are attaching to a sim started
some other way, do it manually in the `pxh>` console — the PX4 subcommand is
`set_ekf_origin`, **not** `set_gps_global_origin`:

```
commander set_ekf_origin 0 0 0
```

Before flying, confirm in the PX4 startup log:

- [ ] All sensor topics publish: optical flow, flow camera, downward
      rangefinder, upward rangefinder, 2D lidar, mono camera
- [ ] `EKF2_GPS_CTRL = 0` (GPS off — the whole point of the project)
- [ ] `EKF2_OF_CTRL = 1` (optical flow feeding the estimator)

## Sensors, before you leave the ground

```bash
pixi run sensors
```

- [ ] Lidar returns a full scan, not a wall of `inf`
- [ ] Compass heading is stable and matches the drone's visible yaw in Gazebo
- [ ] Optical flow reports quality above zero
- [ ] The log shows the sensors on `gz.transport13`, not the CLI fallback — the
      fallback works but costs a fork+exec per sample and will not hold rate

## Full mission — `hangar_circuit_pursuit.py`

The delivery mission. Circuits the hangar wall-following, detects a pigeon,
pursues it, returns to where it broke off, resumes the leg.

```bash
pixi run fly
```

**Flight quality:**

- [ ] Takes off to the commanded altitude and holds it — no slow sag
- [ ] Wall-follow legs track the target distance within roughly ±0.15m
- [ ] Each 90-degree turn ends aligned to the wall, not overshooting
- [ ] After each turn the drone **holds still for ~3s before correcting
      position** — this is deliberate, see `scarecrow/controllers/CLAUDE.md`
- [ ] All four corners complete; total corner time is roughly 45s, not 80s
- [ ] Lands under control near the start position

**Detection and pursuit:**

- [ ] YOLO reports its device at startup: `cuda`, `mps` or `cpu`. On a machine
      with a GPU, `cpu` means the accelerator failed and inference will be slow
- [ ] Pigeon detected during a leg, with the pursuit entry decision logged
- [ ] Drone yaws onto the target and closes to the stop distance
- [ ] Returns to the pursuit entry point and restores its pre-pursuit heading
- [ ] The interrupted leg resumes rather than the circuit restarting

**Output:**

- [ ] Detection frames under `webapp/output/<flight_id>/detections/`
- [ ] Video at `webapp/output/<flight_id>/flight_camera.mp4`
- [ ] Flight row written:
      `sqlite3 webapp/backend/database/scarecrow.db "SELECT * FROM flights ORDER BY start_time DESC LIMIT 1"`
- [ ] No Python traceback anywhere in the flight log

## Mapping — `room_circuit_map.py`

Only when you have touched mapping or `navigation/`.

- [ ] Four legs complete, `MAP_RESULT:` emitted with a non-zero area
- [ ] Map JSON written under `scarecrow/mapped_env/<datetime>/map.json`
- [ ] Recorded distances are plausible against the world's real geometry

## Webapp

- [ ] Connect launches the sim; the per-step substatus advances rather than
      sitting on "active"
- [ ] Both camera streams render — the fixed monitor camera and the drone
      follow camera
- [ ] The telemetry rail populates as the mission logs phases
- [ ] Disconnect leaves **no** surviving processes — see teardown below
- [ ] Connect works again immediately after a Disconnect. `ERROR [px4] Task
      already running` on the second Connect means teardown leaked `px4-mavlink`
      or the `rcS` shell

## Abort

While a mission is flying:

- [ ] The webapp's RESET button disarms the drone and returns it to spawn
- [ ] `kill -TERM <pid>` on the flight script lands the drone rather than
      dropping it, and the flight record ends as `aborted`

## Teardown — do not skip

Leaving PX4 or Gazebo running poisons the next run, and a leaked `mavsdk_server`
squats on udp 14540 so the next flight cannot connect.

```bash
pgrep -fl "px4|gz sim|mavsdk_server|stream_camera"
```

- [ ] Returns nothing once you are done

## Known issues to expect

Normal, not regressions:

- **Altitude sags ~0.6m** during pursuit at a 5.5m target. Marginal, tracked.
- **`--r` (right-hand start) is unverified** — `stabilize_corner()` hardcodes
  the left wall.
- **AMD and Intel GPUs render Gazebo but not YOLO.** Inference falls back to
  CPU, which is several times slower. Slow, not broken.
- **Camera frames are parsed after landing, never during flight** — parsing in
  flight destabilises the drone.
- **Never `param set` an EKF2 value at runtime.** It resets the estimator and
  breaks optical flow.

## If something fails

1. Read the PX4 console first — most flight failures announce themselves there.
2. Check the sensor is actually publishing before suspecting the controller.
   The lidar has been right every time it was doubted.
3. For anything that looks like a control problem, log **commanded velocity
   next to actual velocity** before proposing a fix. Three plausible
   control-theory explanations were wrong; one log line found the real cause.
4. Confirm the sim environment is clean — processes left over from a previous
   run cause failures that look like code bugs.
