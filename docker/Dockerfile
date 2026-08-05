# syntax=docker/dockerfile:1.7
#
# Scarecrow drone simulation image.
#
# Pinning rationale: on 2026-06-20 a `brew upgrade` on the developer Mac moved
# protobuf to 35 (breaking the PX4 -Werror build) and removed assimp entirely
# (Gazebo could not start). Nothing in the repo changed. Homebrew has no
# lockfile; apt on a digest-pinned base image is deterministic by construction.
#
# Build args come from docker/versions.env — never hardcode them here.

ARG UBUNTU_DIGEST

# =====================================================================
# Stage 0: frontend build
# =====================================================================
# Built here rather than shipping webapp/frontend/build from the repo, so the
# image never depends on someone having remembered to run `npm run build`.
#
# Runs in parallel with the PX4 compile (BuildKit) and only re-runs when the
# frontend sources change -- it does not sit in front of the expensive stages.
#
# Node 22, not 24: react-scripts 5 does not build on 24. Same major as the
# pixi environment, so the macOS and Docker tracks build the same bundle.
FROM node:22-bookworm-slim AS webbuild

WORKDIR /build

# package.json + lockfile first: `npm ci` is the slow layer and must not be
# invalidated by an edit to a component.
COPY webapp/frontend/package.json webapp/frontend/package-lock.json ./
RUN npm ci

COPY webapp/frontend/ ./

# Empty API base = same origin. The backend serves this bundle, so the API is
# wherever the page was loaded from. Anything hardcoded here would break as
# soon as the user opens the app from another machine (or from Windows against
# a container in WSL2), which is exactly the delivery scenario.
ENV REACT_APP_API_BASE=""

# CI=true makes react-scripts treat warnings as errors. Off deliberately: a
# lint warning must not fail the customer's delivery build.
ENV CI=false
RUN npm run build

# =====================================================================
# Stage 1: system dependencies
# =====================================================================
FROM ubuntu@${UBUNTU_DIGEST} AS deps

ARG GZ_VERSION
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release sudo git \
 && curl -sSL https://packages.osrfoundation.org/gazebo.gpg \
        -o /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/gazebo-stable.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
        gz-harmonic=${GZ_VERSION} \
        python3-gz-transport13 \
        python3-gz-msgs10 \
        libassimp-dev \
        libopencv-dev \
        cppzmq-dev \
        libunwind-dev \
        libeigen3-dev \
        libxml2-utils \
        protobuf-compiler \
        pkg-config \
        bc dmidecode \
        mesa-utils \
        libgl1-mesa-dri \
        libegl1 \
        python3 python3-venv python3-pip python3-dev \
        build-essential cmake ninja-build \
        ffmpeg \
        procps iproute2 curl \
 && rm -rf /var/lib/apt/lists/*

# Every dependency here is EXPLICIT rather than transitive, on purpose:
#
#   libassimp-dev  -- Gazebo's mesh loader. Disappeared from the developer Mac
#                     on 2026-06-20 as a side effect of an unrelated upgrade
#                     and took Gazebo down with it (could not start at all).
#   libopencv-dev  -- required by the optical_flow gz plugin
#                     (gz_plugins/optical_flow/CMakeLists.txt:40 wants the core
#                     and imgproc components). ubuntu.sh --no-sim-tools does NOT
#                     install it, so the PX4 CMake configure fails without it.
#                     Optical flow is core to GPS-denied navigation here.
#   cppzmq-dev     -- C++ ZeroMQ binding. PX4's gz_bridge and the optical_flow
#                     plugin link CPPZMQ::CPPZMQ. ubuntu.sh adds this ONLY on
#                     Ubuntu 24.04 (see its gazebo_packages block), which is
#                     exactly our base image, and --no-sim-tools skips it.
#   libunwind-dev  -- }
#   libeigen3-dev  -- } the remainder of ubuntu.sh's simulation dependency set,
#   libxml2-utils  -- } which --no-sim-tools omits. Listed explicitly so the
#   protobuf-compiler } image never depends on that flag's behaviour.
#   pkg-config     -- }
#   bc, dmidecode  -- }
#   mesa-utils     -- provides glxinfo for the renderer assertion.
#
# DELIBERATELY OMITTED: the gstreamer1.0-* packages that ubuntu.sh installs.
# They exist only for PX4's GstCameraSystem plugin, which this project does not
# use -- camera streaming goes through scripts/stream_camera.py reading
# Gazebo topics directly. Skipping them keeps the image smaller. If a build
# error ever names GstCameraSystem, add them back here rather than dropping
# --no-sim-tools (which would pull an unpinned Gazebo).

COPY docker/smoke-test.sh /usr/local/bin/smoke-test.sh
RUN chmod +x /usr/local/bin/smoke-test.sh

# =====================================================================
# Stage 2: compile PX4 SITL
# =====================================================================
# Compiled ONCE here, at image build time, with -j$(nproc). The native macOS
# path uses `make -j1` (launch.sh:160), which takes 30-60 minutes on every
# fresh machine. The customer must never pay that cost.
FROM deps AS pxbuild

WORKDIR /opt/scarecrow

# PX4 is CLONED here rather than COPYed from the build context.
#
# WHY: `COPY px4` forces BuildKit to hash and transfer ~49,000 files / 412MB
# through macOS virtiofs on EVERY build -- even when the COPY layer itself is
# cached, because the hash is needed to validate that cache. Measured
# 2026-07-31: 23 minutes and still transferring, before a single line compiled.
# Cloning happens inside the Linux VM at network speed instead, and drops the
# build context from 412MB to ~10MB.
#
# Reproducibility is unchanged: PX4_REF is the exact SHA the repo's gitlink
# already points at. Treat it as a pin -- bump it deliberately, never casually.
ARG PX4_REPO=https://github.com/riftins98/PX4-Autopilot.git
ARG PX4_REF=1104aeddca4260d62b1c91985d9fa4d06b47faef

RUN git clone "${PX4_REPO}" /opt/scarecrow/px4 \
 && cd /opt/scarecrow/px4 \
 && git checkout "${PX4_REF}" \
 && git submodule update --init --recursive \
 && git -C /opt/scarecrow/px4 rev-parse HEAD

COPY docker/requirements-px4.lock /tmp/requirements-px4.lock

# PX4's own dependency installer. --no-sim-tools because gz-harmonic is already
# installed from the pinned OSRF repo above and we do not want it pulling an
# unpinned Gazebo.
RUN /opt/scarecrow/px4/Tools/setup/ubuntu.sh --no-nuttx --no-sim-tools

# Pinned Python toolchain for the build (kconfiglib, empy, jinja2, ...).
RUN python3 -m venv /opt/scarecrow/.venv \
 && /opt/scarecrow/.venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/scarecrow/.venv/bin/pip install --no-cache-dir -r /tmp/requirements-px4.lock

ENV PYTHON_EXECUTABLE=/opt/scarecrow/.venv/bin/python
ENV PATH="/opt/scarecrow/.venv/bin:${PATH}"

RUN cd /opt/scarecrow/px4 && make px4_sitl -j"$(nproc)"

# Also build the nolockstep target.
#
# WHY: PX4 SITL defaults to lockstep -- PX4 waits for Gazebo to finish each
# render step. Inside a container without a GPU, Gazebo software-renders and
# that wait dominates: measured RTF 0.055 on an Apple Silicon Mac versus ~0.5
# natively with Metal. With CONFIG_BOARD_NOLOCKSTEP=y, PX4 runs on wall-clock
# and stops waiting, which is exactly why launch.sh already enables it on WSL
# ("~100% RTF").
#
# Both targets ship so the mode is a runtime choice (SCARECROW_NOLOCKSTEP=1),
# not a rebuild: GPU machines can keep lockstep fidelity, GPU-less ones get
# usable speed. ccache makes this second compile much cheaper than the first.
RUN cd /opt/scarecrow/px4 && make px4_sitl_nolockstep -j"$(nproc)"

RUN test -x /opt/scarecrow/px4/build/px4_sitl_default/bin/px4 \
 || (echo "PX4 binary missing after build" >&2; exit 1)
RUN test -x /opt/scarecrow/px4/build/px4_sitl_nolockstep/bin/px4 \
 || (echo "PX4 nolockstep binary missing after build" >&2; exit 1)

# =====================================================================
# Stage 3: runtime
# =====================================================================
FROM pxbuild AS runtime

# Repo-owned assets. These are small and change often, so they come last —
# editing a flight script or world invalidates only these layers, never the
# PX4 compile above.
COPY scripts   /opt/scarecrow/scripts
COPY scarecrow /opt/scarecrow/scarecrow
COPY worlds    /opt/scarecrow/worlds
COPY models    /opt/scarecrow/models
COPY airframes /opt/scarecrow/airframes
COPY config    /opt/scarecrow/config
COPY requirements.txt /opt/scarecrow/requirements.txt

# The sim launcher depends on webapp backend code, which is not obvious:
# launch_with_stream.sh calls scripts/shell/world_meta.py, which loads
# webapp/backend/services/world_geometry.py by absolute path to resolve the
# default world and spawn pose. Without this COPY the launcher dies with
# FileNotFoundError before Gazebo ever starts. Only 348K, and Step 2 (webapp)
# needs it anyway.
COPY webapp/backend /opt/scarecrow/webapp/backend

# The built UI. app.py mounts this when it exists, so the backend serves the
# whole product on one port -- no Node and no dev server in the runtime image.
COPY --from=webbuild /build/build /opt/scarecrow/webapp/frontend/build

# Runtime Python dependencies, pinned to the exact versions in requirements.txt.
#
# This is the FULL set, not just the stream, because the webapp's
# DetectionService spawns scripts/flight/*.py as subprocesses -- so the image
# needs every dependency those scripts touch:
#   mavsdk        -- all drone control (scarecrow/flight/flight.py)
#   matplotlib    -- sensor_check.py plots
#   ultralytics   -- YOLO pigeon detection (hangar_circuit_pursuit.py,
#                    scarecrow/detection/yolo.py). Pulls torch.
#
# These imports are lazy (inside functions), so a missing one fails mid-flight
# rather than at startup -- which is exactly the kind of late failure this
# image exists to prevent.
#
# NOT installed: rplidar-roboticia, which is for real hardware only and has no
# use in simulation.
RUN /opt/scarecrow/.venv/bin/pip install --no-cache-dir \
        aiohttp==3.13.5 \
        numpy==2.4.4 \
        opencv-python-headless==4.13.0.92 \
        pillow==12.2.0 \
        mavsdk==3.15.3 \
        matplotlib==3.10.8 \
        torch==2.11.0 \
        torchvision==0.26.0 \
        ultralytics==8.4.36 \
        fastapi==0.135.3 \
        uvicorn==0.44.0 \
        aiofiles==25.1.0 \
        'pydantic>=2.0'

# mavsdk ships a bundled mavsdk_server binary, but not for every architecture.
# Fail at BUILD time if it is missing rather than leaving the first flight to
# discover it, since every flight script depends on it.
RUN MS="$(find /opt/scarecrow/.venv -name 'mavsdk_server*' -type f 2>/dev/null | head -1)"; \
    if [ -z "$MS" ]; then \
        echo "WARNING: no bundled mavsdk_server for $(dpkg --print-architecture)." >&2; \
        echo "Flight scripts need MAVSDK_SERVER_ADDRESS/PORT pointing at an external server." >&2; \
    else \
        echo "mavsdk_server: $MS"; \
    fi

# gz-transport's Python bindings come from apt, so they land in
# /usr/lib/python3/dist-packages -- which this venv cannot see, because it was
# created without --system-site-packages. Symlink them in rather than opening
# the whole system site: the venv pins numpy, and exposing Ubuntu's would let
# the two disagree at import time.
#
# Without this the sensors still work, which is the danger. They fall back to
# spawning `gz topic -e -n 1` per sample, and the container runs several times
# slower with nothing in the logs to say why. Measured on the pixi track:
# lidar 6.2Hz vs 29.7Hz, RTF 0.134 vs 0.755. So this fails the BUILD rather
# than shipping a quietly degraded image.
RUN set -eux; \
    SITE="$(/opt/scarecrow/.venv/bin/python -c 'import site; print(site.getsitepackages()[0])')"; \
    for pkg in /usr/lib/python3/dist-packages/gz*; do \
        if [ -e "$pkg" ]; then ln -sfn "$pkg" "$SITE/$(basename "$pkg")"; fi; \
    done; \
    /opt/scarecrow/.venv/bin/python -c \
        "from gz.transport13 import Node; from gz.msgs10.laserscan_pb2 import LaserScan; print('gz-transport bindings OK')"

COPY docker /opt/scarecrow/docker
RUN chmod +x /opt/scarecrow/docker/*.sh

ENV PATH="/opt/scarecrow/.venv/bin:${PATH}" \
    PYTHONPATH="/opt/scarecrow" \
    PYTHONUNBUFFERED=1 \
    WORLD=hangar_small \
    CAMERA=fixed \
    STREAM_PORT=8080 \
    REQUIRE_GPU=0 \
    SCARECROW_MODE=webapp \
    WEBAPP_PORT=8000

# --- NVIDIA container runtime ------------------------------------------------
# NVIDIA_DRIVER_CAPABILITIES is the single most important line here for the
# Windows/Linux GPU delivery.
#
# nvidia-container-toolkit defaults to "compute,utility". That gives a working
# nvidia-smi and working CUDA -- so every obvious check passes -- but it does
# NOT mount the driver's OpenGL/EGL libraries or install
# /usr/share/glvnd/egl_vendor.d/10_nvidia.json. Gazebo then finds only Mesa,
# silently renders every camera and gpu_lidar on the CPU, and the only symptom
# is that the sim is mysteriously slow. "graphics" is what fixes that; "display"
# covers the GLX case if anyone ever attaches a display.
#
# Set in the image rather than only in docker-compose.yml so a plain
# `docker run --gpus all scarecrow-sim` behaves correctly too.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display

WORKDIR /opt/scarecrow
# 8000 = webapp (UI + REST API), 8080 = camera stream.
EXPOSE 8000 8080

ENTRYPOINT ["/opt/scarecrow/docker/entrypoint.sh"]
