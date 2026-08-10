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

## Partly verified on the target machines

**The amd64 image builds, and reaches a real GPU under WSL2.** Confirmed on
Windows with an AMD Radeon RX 7600S: `bash docker/build.sh` completes natively
in about seven minutes, `detect-gpu.sh` selects the WSL overlay from
`/dev/dxg`, and Mesa reports `D3D12 (AMD Radeon RX 7600S)`. That last part
required `GALLIUM_DRIVER=d3d12` — without it Mesa silently chose llvmpipe even
though the device, the WSL driver libraries and `d3d12_dri.so` were all present
and correct. See the traps in `docker/CLAUDE.md`.

**NVIDIA under WSL2 is verified on an RTX 5090 Laptop.** Docker Engine +
nvidia-container-toolkit inside the distro; `detect-gpu.sh` selects
`nvidia-wsl` (NVIDIA overlay + WSL d3d12 overlay, plus
`MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA`). Headless missions on `hangar_small`
have held ~1.0 real-time factor. The Gazebo GUI via WSLg can open but is still
unreliable — use headless for demos.

**The native-Linux DRI path has never run on target hardware.**
`docker/compose.gpu-dri.yml` is written from the documented mechanisms only.

*To close:* `bash docker/verify-delivery.sh` on each class of machine, then one
full mission with the checklist in `docs/ACCEPTANCE_CHECKLIST.md`.

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

**YOLO inference size is fixed at `imgsz=1280`, and must stay there.** On AMD
and Intel machines inference runs on the CPU and competes with Gazebo for the
same cores, which makes lowering it the obvious optimisation. It does not work.
Measured on CPU against 32 real frames from a recorded flight:

    imgsz    cost         pigeon found    mean confidence
    1280     203 ms/f     7/32            0.519
     960     122 ms/f     4/32            0.061
     640      70 ms/f     0/32            0.000
     480      51 ms/f     0/32            0.000

The target is small in frame at the distances the mission flies, so
downscaling erases it — 640 is three times faster at detecting nothing. Treat
1280 as a floor, not a default: the cost is what the feature costs.

*Symptom of the real problem:* the startup log says `device=cpu` and frame rate
falls while detection is active. The remedy is an accelerator or a slower
detector rate limit, never a smaller image.

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
- **`models/ceiling_net/` (7.6 MB) is kept although no world includes it.** The
  drone carries an upward rangefinder and the mission has a ceiling-clearance
  phase, which only mean anything in a roofed world. This is the asset that
  builds one. Weight with no consumer *today* — not dead weight.
