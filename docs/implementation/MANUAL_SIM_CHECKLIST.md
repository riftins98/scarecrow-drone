# Manual Simulation Verification Checklist

Automated tests cover the code that CAN be tested without real flight (layered webapp, algorithms, repositories). This checklist covers what only a real Gazebo+PX4 sim run can verify.

Use this after any change to:
- `scarecrow/controllers/*`
- `scarecrow/sensors/*/gazebo.py`
- `scarecrow/flight/*`
- `scripts/flight/*`
- Any PX4 airframe or world file

## Setup (required before any flight test)

```bash
source scripts/shell/env.sh
./scripts/shell/launch.sh drone_garage
# In pxh> console (PX4 subcommand is `set_ekf_origin`, NOT `set_gps_global_origin`):
commander set_ekf_origin 0 0 0
```

Verify PX4 logs show:
- [ ] All 5 sensor topics publishing (optical_flow, flow_camera, rangefinder, 2D lidar, mono camera)
- [ ] EKF2_GPS_CTRL = 0
- [ ] EKF2_OF_CTRL = 1

## Baseline Flight (after ANY drone code change)

Run `python3 scripts/flight/demo_flight.py` and verify:

- [ ] Drone arms without error
- [ ] Drone takes off to 2.5m (not just barely off the ground)
- [ ] Drone hovers stably for HOVER_DURATION (no oscillation, no drift into walls)
- [ ] YOLO detects the pigeon billboard
- [ ] Detection images saved to `webapp/output/<flight_id>/detections/`
- [ ] Drone lands at takeoff position (not drifted far from origin)
- [ ] Video built to `webapp/output/<flight_id>/flight_camera.mp4`
- [ ] DB updated: `sqlite3 webapp/backend/database/scarecrow.db "SELECT * FROM flights ORDER BY start_time DESC LIMIT 1"`

## Room Circuit (when modifying wall_follow or rotation)

Run `python3 scripts/flight/room_circuit.py` and verify:

- [ ] Drone flies 4 legs without crashing into walls
- [ ] Each rotation aligns cleanly (not overshooting by more than a few degrees)
- [ ] Drone stabilizes after each turn before next leg
- [ ] Lands near starting position (within 2m)

## UC5 Chase Verification (Phase 5 only)

Run detection flight in `drone_garage` world. Verify:

- [ ] `CHASE_START:pursuit` appears when pigeon detected
- [ ] Drone yaws toward billboard visibly
- [ ] Drone moves forward during pursuit
- [ ] Counter-measure phase: oscillating yaw
- [ ] `CHASE_END:lost` when billboard exits frame or timeout
- [ ] Patrol resumes after chase
- [ ] `chase_events` table has row with correct outcome

## UC7 Abort Verification (Phase 6 only)

While demo_flight.py is hovering:

```bash
# Get PID
pgrep -f demo_flight.py
# Send SIGTERM
kill -TERM <pid>
```

Verify:
- [ ] `ABORT_REQUESTED` printed to stdout
- [ ] Drone lands safely (not falls)
- [ ] Flight record: status = "aborted"
- [ ] Output directory has partial data preserved

## UC1 Mapping Verification (Phase 3 only)

Run `python3 scripts/flight/map_area.py --map-name TestRoom`:

- [ ] `MAP_STATUS:leg_1` through `leg_4` emitted
- [ ] `MAP_POINT:{json}` lines with reasonable distances
- [ ] `MAP_RESULT:{json}` at end with area_size > 0
- [ ] `area_maps` row created with status='active'

## Known Issues

- **indoor_room.sdf**: drone drifts into walls and crashes after ~4s. Use `drone_garage` for development until this is fixed.
- **GStreamer on Mac**: broken. Video uses PNG+ffmpeg workaround (implemented in GazeboCamera).
- **Camera frame parsing during flight**: DO NOT parse raw frames during flight — it destabilizes the drone. Save raw bytes, parse after landing.
- **EKF param set at runtime**: Never do this. It resets the estimator and breaks optical flow.

## If a test fails

1. Check PX4 console for errors
2. Check lidar topic via `gz topic -e -n 1 -t <topic>` to verify data
3. Grep flight script stdout for the failed step
4. Before debugging drone code, verify the sim environment is clean (kill old processes, restart)
