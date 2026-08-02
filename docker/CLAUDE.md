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

macOS does **not** use this. Docker Desktop exposes no GPU there at all, so
Gazebo falls back to software rendering and the simulator runs far too slowly
to fly. macOS uses pixi. See the header of `pixi.toml`.

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
- `detect-gpu.sh` — Chooses the GPU overlay for this machine and writes
  `COMPOSE_FILE` into `.env`. Run by `build.sh`; safe to re-run. `--print`
  reports the value without writing. Checks in the same order as
  `verify-delivery.sh`: NVIDIA runtime, then `/dev/dxg`, then `/dev/dri`.
- `compose.gpu.yml`, `compose.gpu-wsl.yml`, `compose.gpu-dri.yml` — GPU
  overlays; see below.
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

One service, `sim`, plus overlay files that modify it in place. `detect-gpu.sh`
picks one and writes `COMPOSE_FILE` into `.env`, so a bare `docker compose up`
is correct on any machine and the customer never chooses. All overlays set
`REQUIRE_GPU=1`, so a path that does not reach the GPU fails loudly instead of
silently rendering on CPU.

| overlay | for | mechanism |
|---|---|---|
| `compose.gpu.yml` | NVIDIA, Windows/WSL2 or Linux | nvidia-container-toolkit |
| `compose.gpu-wsl.yml` | **any** GPU on Windows (AMD/Intel/NVIDIA) | `/dev/dxg` + Mesa d3d12 |
| `compose.gpu-dri.yml` | AMD or Intel on native Linux | `/dev/dri` |

The image carries the Mesa drivers for all of these — `d3d12_dri.so`,
`radeonsi_dri.so`, `iris_dri.so` and `zink_dri.so` are all present in
`/usr/lib/x86_64-linux-gnu/dri/`, confirmed on the amd64 image. Device
passthrough differs, and so does driver *selection*: see the WSL2 trap below.

**These were Compose profiles on services that `extends: sim`, which was a
bug.** `extends` copies the base service's four published ports, so activating
a profile started *two* containers competing for 8000, 8080, 14540 and 14550 —
and the failure named a port, not a profile. `verify-delivery.sh` avoided it by
naming the service explicitly; the documented `docker compose --profile gpu up`
did not. Overlays modify the one service instead, so a second container cannot
exist. Note that `extends` **appends** profile lists rather than replacing
them, and `!reset` clears them entirely — neither gives a child its own profile,
which is why this could not be fixed in place.

### Four traps, all of which cost real debugging

**WSL2 needs `GALLIUM_DRIVER=d3d12` explicitly.** Everything can be present and
correct — `/dev/dxg` passed through, `/usr/lib/wsl/lib` mounted with
`libdxcore.so`, `d3d12_dri.so` sitting in the image — and Mesa will still
select llvmpipe. Measured on an AMD Radeon RX 7600S under WSL2:

    (unset)                        llvmpipe (LLVM 20.1.2, 256 bits)
    MESA_LOADER_DRIVER_OVERRIDE    llvmpipe
    GALLIUM_DRIVER=d3d12           D3D12 (AMD Radeon RX 7600S)

`MESA_LOADER_DRIVER_OVERRIDE` is the obvious variable and it does nothing here:
it drives the DRI loader, which enumerates DRM nodes under `/dev/dri`, and WSL2
has no `/dev/dri` at all. d3d12 is a Gallium driver reached through dxcore and
`/dev/dxg`, so `GALLIUM_DRIVER` is what selects it. Set in
`compose.gpu-wsl.yml`.

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
- **MJPEG is the only stream transport, here and on macOS.** A WebRTC
  streamer used to exist and has been deleted. It could not work in a
  container: ICE negotiates media over dynamic UDP ports and advertises the
  container's internal address, which on Docker Desktop lives inside the VM
  and is unreachable from the host browser. Only the published TCP port
  crosses that boundary, so signalling succeeded (the page loaded) while media
  never connected — observed 2026-07-31, nine peer connections all stuck at
  pc_state=connecting, black video. Restoring it would need a TURN server or a
  fixed published UDP range with forced ICE candidates. MJPEG is plain HTTP
  multipart over the one published port and works through any port mapping.
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
  logs — the sim still flies, just badly, which is the hardest kind of fault to
  notice on someone else's machine. The Dockerfile asserts the import at
  **build** time so a broken binding fails the build instead of shipping a
  quietly degraded image.

## Validation status

**arm64/macOS**: image self-test passes in full, and `verify-delivery.sh`
passes in `--no-gpu` mode — UI served, Connect launches without rebuilding PX4,
the stream carries real JPEG frames, every sensor group reports through the
flight subprocess.

**amd64/Windows+WSL2, AMD Radeon RX 7600S**: the image **builds** (428s,
native), `detect-gpu.sh` correctly selects the WSL overlay from `/dev/dxg`, and
Mesa reaches the real GPU — `D3D12 (AMD Radeon RX 7600S)` — once
`GALLIUM_DRIVER=d3d12` is set. `REQUIRE_GPU=1` correctly refused to start on
llvmpipe before that was fixed, which is exactly its job.

Still open:
- **No full mission has been flown on Windows.** Rendering reaches the GPU;
  whether the simulator holds real-time factor there is unmeasured, and
  `SCARECROW_NOLOCKSTEP=0` on the GPU paths is still an assumption carried
  over from native Metal.
- **NVIDIA and native-Linux DRI paths remain unverified.** Only the WSL2 path
  has run on real hardware.
