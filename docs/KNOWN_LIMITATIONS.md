# Known Limitations

Everything below is known and unresolved. It is written down so you read it
here rather than discover it during a demonstration.

Each entry says what the limitation is, how it shows up, and what closing it
would take.

## Never run on real hardware

**The hardware sensor drivers have never touched a drone.** `lidar/rplidar.py`
(RPLidar A1M8), `rangefinder/tfluna.py` (TF-Luna) and `camera/picamera.py`
(Pi Camera 3) are written against the same interfaces their simulated
counterparts implement, and they are unit-tested — `tfluna.py`'s frame parser
especially, because that sensor sets flight altitude and a byte-order slip
flies the drone into a roof. But unit tests prove the parsing, not the wiring.
Nothing here has read a real serial port.

*To close:* bring up one sensor at a time on the Pi with the drone on the
ground, comparing each reading against a tape measure before arming anything.

**Expect the estimator to behave worse than in simulation.** After a 90-degree
rotation PX4's velocity estimate disagrees with the lidar for several seconds,
because rotational flow contaminates optical flow's translational estimate.
The mission handles this by holding still before correcting position (see
`scarecrow/controllers/CLAUDE.md`). Real optical flow is noisier than
simulated, so the recovery is unlikely to be *shorter* on hardware. Any new
manoeuvre that rotates and then holds position needs the same treatment.

## Never built or run on the target machines

**The amd64 Docker image has never been built.** Development was on Apple
Silicon, and cross-building amd64 there takes hours. The Dockerfile pins
everything it needs, but "pins correctly" and "builds" are different claims.

*To close:* `bash docker/build.sh` on an amd64 host.

**GPU passthrough has never run, on any vendor.** All three compose overlays
(`docker/compose.gpu.yml`, `compose.gpu-wsl.yml`, `compose.gpu-dri.yml`) are
written from the documented mechanisms and verified only in `--no-gpu` mode. `docker/CLAUDE.md` records three traps that
cost real debugging, including WSL silently falling back to "Microsoft Basic
Render Driver" — software rendering that looks like a working GPU.

*To close:* `bash docker/verify-delivery.sh` **on the target machine**. This is
the acceptance test, and it is what actually decides whether the delivery
works.

## Flight behaviour

**Altitude sags roughly 0.6 m during pursuit** at a 5.5 m target. The margin is
thin rather than broken. It was masked while the simulator ran slowly: at low
real-time factor the altitude loop got more corrections per simulated second
than the real drone will get at 20 Hz.

*To close:* raise the altitude loop's authority during pursuit, or lower the
pursuit target.

**`--r` (right-hand start) is unverified.** `stabilize_corner()` hardcodes the
left wall regardless of `start_side`, so a right-hand circuit would stabilise
against the wrong wall. Every flight to date has been left-hand.

*To close:* pass `start_side` through and fly it once.

**The position loop trusts PX4's frame.** The durable fix for the rotation
problem above is to close the loop on lidar-derived velocity instead, which
would make the mission immune rather than patient. Not attempted.

## Platform

**Only NVIDIA and Apple accelerate YOLO.** An AMD or Intel host renders Gazebo
correctly but has no torch backend, so inference falls back to CPU — several
times slower, and competing with `gz sim` for the same cores. It works; it is
slow. The device is logged at startup, so a GPU machine reporting `cpu` means
the accelerator failed rather than that none exists.

**Camera recording is unwired.** The PNG+ffmpeg video path exists and is
unit-tested, but the mission prints "Camera recording: disabled" and
`RecordingService` holds no camera, so it is never exercised in a live run.

**Two Gazebo models are unused** — `models/ceiling_net/` (7.6 MB) and
`models/pigeon_billboard/` (596 KB). Both belong to worlds that no longer
exist. Harmless, but they are repository weight with no consumer.

## Tuning on a machine that is not the developer's Mac

Every performance choice here was measured on Apple Silicon with a Metal
accelerator. They are reasonable defaults, not tuned values, and two of them
are likely wrong on a Windows laptop reaching its GPU through WSL2.

**Lockstep is on for every GPU path.** `SCARECROW_NOLOCKSTEP=0` assumes
rendering is fast enough that PX4 waiting on each frame costs little. That was
true on native Metal. WSL2 reaches the GPU through d3d12 paravirtualisation,
where every render call crosses a VM boundary, and a laptop GPU will throttle
over a five-minute mission. If real-time factor is poor, try:

    SCARECROW_NOLOCKSTEP=1 docker compose up

*Symptom:* the simulation runs slowly but the renderer check passes and the GPU
is clearly in use.

**YOLO inference size is hardcoded at `imgsz=1280`** in
`scarecrow/detection/yolo.py`. That size was chosen because an accelerator
absorbed it. On any AMD or Intel machine inference falls to the CPU and then
competes with Gazebo for the same cores — on this project, moving YOLO off the
CPU was the single largest performance improvement ever measured, and those
machines get none of it. There is currently no configuration knob; lowering it
means editing the literal.

*Symptom:* the startup log says `device=cpu`, frame rate falls while detection
is active, and the simulator recovers when the drone is not looking at
anything.

**Camera resolutions were chosen against Metal too** — a 1080p monitor camera,
two 720p cameras and two GPU lidars, all rendered every frame. Render cost
scales with resolution times update rate, and on this stack update rate costs
more than resolution. `models/*/model.sdf` is where to change either.

The honest position: nobody has measured any of this on Windows. One run of
`docker/verify-delivery.sh` plus one full mission gives more information than
all of the above reasoning.

## Scope, by choice

These are not defects. They are decisions, recorded so nobody spends a week
rediscovering the reasoning.

- **Mapping produces an axis-aligned bounding box, not SLAM.** Full SLAM was
  out of scope for the project.
- **`Flight` (the lifecycle orchestrator) is unused.** The hangar mission owns
  its own phase sequence. `Flight` is scaffolding for a future mission that
  wants a reusable lifecycle.
- **GStreamer is not used and not installed.** It is a pipeline framework, not
  a wire format, so it would not make streaming cross-platform — and it is
  broken on macOS, so it would create an OS split rather than remove one.
- **The pigeon is teleported, never deleted.** Removing a model from a running
  Gazebo world segfaults the server.
