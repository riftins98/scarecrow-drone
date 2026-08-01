# docker

Delivery image for Windows and Linux: the **whole product** — webapp UI, REST
API, PX4 SITL and Gazebo — in one container.

```bash
docker compose up            # -> http://localhost:8000/
```

That URL is the entire interface. The container starts only the backend; the
user picks world/camera/spawn in the UI and presses Connect to launch the sim.
There is deliberately no other way in — the sim is the product, the UI is how
the product is used.

macOS does **not** use this. Docker Desktop exposes no GPU there (measured RTF
0.055 vs 0.87 native), so macOS uses pixi. See the header of `pixi.toml`.

## Files
- `Dockerfile` — 4 stages. `webbuild` (Node 22) builds the React bundle;
  `deps` installs apt packages onto a digest-pinned Ubuntu; `pxbuild` clones
  PX4 at a pinned SHA and compiles SITL; `runtime` adds repo assets, Python
  deps and the built UI. PX4 is cloned rather than COPYed so the build context
  stays ~10MB (BuildKit hashes the whole context on every build).
- `entrypoint.sh` — Checks the renderer, runs a Gazebo preflight, then starts
  the backend (`SCARECROW_MODE=webapp`, the default) or the headless sim
  (`SCARECROW_MODE=sim`, for CI/debugging). Any explicit command is passed
  through, so `docker run <image> bash` works for inspection.
- `check-renderer.sh` — Detects software rendering. Fatal when `REQUIRE_GPU=1`.
- `smoke-test.sh` — Preflight: proves a Gazebo server can start and publish
  `/clock` before PX4 is launched.
- `build.sh` — **Use this instead of `docker compose build`.** Sources
  `versions.env` (a plain compose build produces `FROM ubuntu@` and fails) and
  prunes the images/cache the rebuild orphaned.
- `self-test.sh` — Runs **inside** the image, needs no GPU. Proves nothing is
  missing. See below.
- `verify-delivery.sh` — Acceptance test. **Run on the target machine before
  handing over.** Auto-detects the GPU path; `--no-gpu` skips the GPU checks.
- `versions.env` — The two pins (Ubuntu digest, Gazebo version).
- `requirements-px4.lock` — PX4's build-time Python deps, pinned.

## The two test scripts, and why there are two

They answer different questions, and conflating them is how you end up
debugging the wrong thing:

| | question | needs a GPU? |
|---|---|---|
| `self-test.sh` | is anything **missing from the image**? | no |
| `verify-delivery.sh` | does it **work on this machine**? | yes |

Both failures look identical from the outside — the sim renders in software —
so `verify-delivery.sh` runs `self-test.sh` first and reports them separately.

`self-test.sh` also tests the renderer guard against **recorded `eglinfo`
output from real NVIDIA, AMD, Intel and WSL machines**, so the classification
is verified on hardware the developer machine has never had. That is how the
"Microsoft Basic Render Driver" bug below was caught on a Mac.

## GPU

Compose profiles, because the delivery laptops and whatever a future student
owns are not the same hardware. All set `REQUIRE_GPU=1`, so a profile that does
not reach the GPU fails loudly instead of silently rendering on CPU.

| profile | for | mechanism |
|---|---|---|
| `gpu` | NVIDIA, Windows/WSL2 or Linux | nvidia-container-toolkit |
| `gpu-wsl` | **any** GPU on Windows (AMD/Intel/NVIDIA) | `/dev/dxg` + Mesa d3d12 |
| `gpu-dri` | AMD or Intel on native Linux | `/dev/dri` |

The image already carries the Mesa drivers for all of these (`d3d12`,
`radeonsi`, `iris`, `zink`); only device passthrough differs.

### Three traps, all of which cost real debugging

**`NVIDIA_DRIVER_CAPABILITIES` must include `graphics`.** The toolkit defaults
to `compute,utility` — CUDA and `nvidia-smi` work, so every obvious check
passes, but the driver's OpenGL/EGL libraries are never mounted and Gazebo
silently renders on the CPU. The Dockerfile sets
`compute,utility,graphics,display`.

**The renderer probe uses EGL, not `glxinfo`.** The container is headless with
no `DISPLAY`, so `glxinfo` prints only "unable to open display". An earlier
version used it, which meant `--profile gpu` would have reported "unknown" and
refused to start on a perfectly good RTX 5090. EGL's surfaceless platform needs
no display and is the same path OGRE2 uses for offscreen rendering.

**"Microsoft Basic Render Driver" is software.** On WSL2 it arrives through the
*same* Mesa d3d12 driver a working GPU does, so any check that reasons "d3d12
means hardware" accepts it — and WSL falls back to it silently whenever the
real GPU is not exposed to the container. It is the most likely way this ships
to someone and quietly flies the whole sim on CPU. Explicitly rejected, along
with `lavapipe` and VMware's `SVGA3D`.

## Known deliberate choices
- **MJPEG, not WebRTC** (`STREAM_MODE=mjpeg`). WebRTC's ICE media path cannot
  cross Docker port mapping: signalling connects, video stays black.
- **`SCARECROW_NOLOCKSTEP=1` on CPU, `0` on the GPU profiles.** Nolockstep
  exists to stop PX4 waiting on a slow software renderer; with a real GPU,
  lockstep is PX4's intended mode and gives deterministic sensor timing.
- **GStreamer is not installed.** PX4's `gstreamer/CMakeLists.txt` drops
  `GSTREAMER_LIBRARY_DIRS`, and the streaming path here does not need it.
  GStreamer is a pipeline *framework*, not a wire format, so adopting it would
  not make streaming cross-platform — and it is broken on macOS, so it would
  create an OS split rather than remove one.
- **gz-transport Python bindings are symlinked into the venv.** They come from
  apt (`python3-gz-transport13`, `python3-gz-msgs10`) and land in
  `/usr/lib/python3/dist-packages`, which the venv cannot see — it is created
  without `--system-site-packages` deliberately, since it pins numpy. Without
  the symlink every sensor silently falls back to spawning `gz topic -e -n 1`
  per sample and the container runs several times slower with nothing in the
  logs. Measured on pixi: lidar 6.2Hz vs 29.7Hz, RTF 0.134 vs 0.906. The
  Dockerfile asserts the import at **build** time so a broken binding fails the
  build instead of shipping a quietly degraded image.

## Validation status
Verified end to end on **arm64/macOS**: 43/43 image self-test checks, and
15/15 delivery checks in `--no-gpu` mode (UI served, Connect launches without
rebuilding PX4, ~79 MJPEG frames in 8s, all four sensor groups via the flight
subprocess).

Still open, and neither is fixable from a Mac:
- the **amd64** image must be built **on an amd64 host** — cross-building on
  Apple Silicon takes hours
- **GPU rendering is unverified on every path.** Run `verify-delivery.sh` on
  the target machine; that is what decides whether the delivery works.
