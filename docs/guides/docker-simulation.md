# Docker simulation commands (Windows / WSL2 / Linux)

All commands run **inside WSL2 Ubuntu** (or native Linux), from the repo root
on the Linux filesystem — e.g. `~/scarecrow-drone`, **not** `/mnt/c/...`.

On this machine the Docker group may not apply until you open a new shell.
If `docker` asks for root, prefix with `sg docker -c '...'` or use a fresh
terminal after `sudo usermod -aG docker $USER`.

---

## One-time setup

```bash
cd ~/scarecrow-drone

# Build the image (sources docker/versions.env; do not use bare compose build)
bash docker/build.sh

# Record the GPU overlay for this machine into .env
bash docker/detect-gpu.sh
bash docker/detect-gpu.sh --print    # show only, do not write
```

Optional acceptance check on the target machine:

```bash
bash docker/verify-delivery.sh
# bash docker/verify-delivery.sh --no-gpu   # skip GPU checks
```

Image-only check (no GPU required):

```bash
docker run --rm scarecrow-sim:dev /opt/scarecrow/docker/self-test.sh
```

---

## Path A — Web console (recommended product UI)

Starts the backend + built UI. You pick world / camera / spawn in the browser,
then press **Connect**.

```bash
cd ~/scarecrow-drone
docker compose up
```

Detached:

```bash
docker compose up -d
docker compose ps
docker compose logs -f sim
```

Open **http://localhost:8000/** in your Windows (or host) browser.

| Port | Use |
|------|-----|
| `8000` | Web UI + API |
| `8080` | Camera MJPEG stream (after Connect in headless mode) |
| `14540/udp` | PX4 MAVSDK |
| `14550/udp` | QGroundControl |

Stop:

```bash
docker compose down --remove-orphans
```

**Display tips (WSL):** Prefer **Headless** in the UI for reliable RTF. GUI
needs WSLg; if the Gazebo window flashes and closes, use Headless.

Optional RTF-oriented override in `.env` (no image rebuild):

```bash
# append or edit ~/scarecrow-drone/.env
echo 'SCARECROW_NOLOCKSTEP=1' >> .env
docker compose up
```

---

## Path B — Shell workflow (like macOS `pixi run sim` / `fly`)

### Terminal 1 — start the simulator

Headless + fixed overhead camera (best on WSL):

```bash
bash docker/sim.sh sim --headless --fixed
```

With an explicit world:

```bash
bash docker/sim.sh sim hangar_small --headless --fixed
bash docker/sim.sh sim hangar_lite --headless --fixed
```

Gazebo GUI window (needs WSLg on Windows 11):

```bash
bash docker/sim.sh sim hangar_small --fixed
# omit --headless → GUI; --fixed is the stream camera, not “fix”
```

Other camera flags (same as `launch_with_stream.sh`):

```bash
bash docker/sim.sh sim --headless --drone_cam
bash docker/sim.sh sim --headless --drone_view hangar_lite
```

Stream while this is running: **http://localhost:8080/**

### Terminal 2 — fly / diagnose

```bash
bash docker/sim.sh fly
bash docker/sim.sh fly --wall-distance 2.5 --target-alt 4.0
bash docker/sim.sh fly --wall-distance 2 --start-side left

bash docker/sim.sh sensors
bash docker/sim.sh map
bash docker/sim.sh shell
```

Stop the shell-workflow stack:

```bash
bash docker/sim.sh down
```

| macOS (`pixi`) | Docker (`sim.sh`) |
|----------------|-------------------|
| `pixi run sim` | `bash docker/sim.sh sim --headless --fixed` |
| `pixi run fly` | `bash docker/sim.sh fly` |
| `pixi run sensors` | `bash docker/sim.sh sensors` |
| `pixi run launch` (GUI) | `bash docker/sim.sh sim --fixed` |

---

## Everyday lifecycle

```bash
# Start product UI (uses the *already built* image — not live repo files)
docker compose up

# After editing worlds/, models/, scripts/, scarecrow/, airframes/, config/,
# or webapp/ — rebuild then restart (required; compose up alone will not see it)
bash docker/deploy.sh
# bash docker/deploy.sh --no-up    # rebuild only

# Or restart after .env / GPU overlay changes only (no image rebuild)
docker compose down --remove-orphans
bash docker/detect-gpu.sh
docker compose up

# Full rebuild after Dockerfile / dependency pin changes
bash docker/build.sh

# Confirm nothing scarecrow-related is left
docker compose down --remove-orphans
bash docker/sim.sh down
docker ps
```

**What needs `deploy.sh` / `build.sh`?** Anything COPYed into the image:
`worlds/`, `models/`, `scripts/`, `scarecrow/`, `airframes/`, `config/`,
`webapp/`. A new `worlds/my_hangar.sdf` is invisible until you rebuild.

**What does not?** `.env` / GPU overlays (`detect-gpu.sh`), then
`docker compose up` again.
---

## Quick troubleshooting commands

```bash
# What GPU path will compose use?
bash docker/detect-gpu.sh --print
grep -E '^(COMPOSE_FILE|MESA_|SCARECROW_)' .env

# Renderer / devices inside a running webapp container
docker compose exec sim bash -lc 'echo DISPLAY=$DISPLAY; eglinfo -B 2>/dev/null | grep -i renderer; ls -l /dev/dxg /dev/dri 2>&1'

# nvidia-smi in an NVIDIA runtime container
docker run --rm --gpus all scarecrow-sim:dev nvidia-smi -L

# Rough RTF from /clock (sim must be flying)
docker compose exec sim bash -lc 'timeout 3 gz topic -e -t /clock -n 1'
```

If `docker` prints Docker Desktop’s “activate WSL integration” stub, you are
hitting the Windows `docker.exe` shim — use Docker Engine inside WSL
(`which -a docker` should prefer `/usr/bin/docker`).

---

## See also

- [README — Quick start](../../README.md#quick-start)
- [docker/CLAUDE.md](../../docker/CLAUDE.md) — GPU overlays and traps
- [Simulation CLI guide](simulation-cli.md) — native/pixi-oriented walkthrough
- [Webapp user guide](simulation-webapp.md) — HUD console
- [Known limitations](../KNOWN_LIMITATIONS.md)
