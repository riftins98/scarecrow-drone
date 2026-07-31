#!/usr/bin/env bash
# Acceptance test for the delivered Docker image.
#
# RUN THIS ON THE TARGET MACHINE (Windows/WSL2 + NVIDIA, or Linux + NVIDIA)
# BEFORE HANDING THE SYSTEM OVER. It is the test the developer Mac cannot run:
# everything below except the GPU checks was verified on arm64/macOS, but GPU
# passthrough is the one thing that decides whether the delivery actually
# works, and it can only be proven on the target hardware.
#
#   bash docker/verify-delivery.sh
#
# Exit 0 = the system is ready to hand over. Any failure is explained inline
# with what to do about it. Nothing here modifies the image.

set -uo pipefail

# Which GPU path to verify. Auto-detected by default, because the machine this
# is handed to may be NVIDIA (the delivery laptops) or AMD/Intel (whatever a
# future student happens to own).
#
#   bash docker/verify-delivery.sh                # auto-detect
#   bash docker/verify-delivery.sh --gpu nvidia   # force a path
#   bash docker/verify-delivery.sh --gpu wsl      # any vendor, Windows/WSL2
#   bash docker/verify-delivery.sh --gpu dri      # AMD/Intel on native Linux
#   bash docker/verify-delivery.sh --no-gpu       # skip GPU checks entirely
#
# --no-gpu exists so the wiring can be exercised without a GPU (the developer
# Mac, CI). It is NOT a substitute for the real run: passing with --no-gpu says
# nothing about whether the target machine will render on its GPU.
GPU_KIND="auto"
for arg in "$@"; do
    case "$arg" in
        --no-gpu) GPU_KIND="none" ;;
        --gpu) NEXT_IS_KIND=1 ;;
        --gpu=*) GPU_KIND="${arg#--gpu=}" ;;
        nvidia|wsl|dri|none|auto)
            if [ "${NEXT_IS_KIND:-0}" = "1" ]; then GPU_KIND="$arg"; NEXT_IS_KIND=0
            else echo "unexpected argument: $arg" >&2; exit 2; fi ;;
        -h|--help) sed -n '2,32p' "$0"; exit 0 ;;
        *) echo "unknown argument: $arg" >&2; exit 2 ;;
    esac
done

if [ "$GPU_KIND" = "auto" ]; then
    if docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; then
        GPU_KIND="nvidia"
    elif [ -e /dev/dxg ]; then
        GPU_KIND="wsl"
    elif [ -e /dev/dri ]; then
        GPU_KIND="dri"
    else
        GPU_KIND="none"
    fi
    echo "[auto-detect] GPU path: $GPU_KIND"
fi

case "$GPU_KIND" in
    nvidia) COMPOSE_PROFILE="gpu";     SERVICE="sim-gpu" ;;
    wsl)    COMPOSE_PROFILE="gpu-wsl"; SERVICE="sim-gpu-wsl" ;;
    dri)    COMPOSE_PROFILE="gpu-dri"; SERVICE="sim-gpu-dri" ;;
    none)   COMPOSE_PROFILE="none";    SERVICE="sim" ;;
    *) echo "unknown --gpu value: $GPU_KIND (want nvidia|wsl|dri|none)" >&2; exit 2 ;;
esac
GPU_MODE=1
[ "$GPU_KIND" = "none" ] && GPU_MODE=0

WEBAPP="http://localhost:${WEBAPP_PORT:-8000}"
STREAM="http://localhost:${STREAM_PORT:-8080}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PASS=0
FAIL=0
WARN=0

ok()   { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
bad()  { echo "  [FAIL] $*" >&2; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $*"; WARN=$((WARN + 1)); }
step() { echo; echo "=== $* ==="; }

cd "$REPO_ROOT"

# versions.env carries the pinned base image digest and Gazebo version.
if [ -f docker/versions.env ]; then
    set -a
    # shellcheck disable=SC1091
    . docker/versions.env
    set +a
fi

cleanup() {
    echo
    echo "=== Tearing down ==="
    docker compose --profile "$COMPOSE_PROFILE" down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---------------------------------------------------------------------
step "1. Host prerequisites"
# ---------------------------------------------------------------------
if docker info >/dev/null 2>&1; then
    ok "Docker daemon reachable"
else
    bad "Docker daemon not reachable. Start Docker Desktop (Windows) or dockerd (Linux)."
    exit 1
fi

HOST_ARCH="$(docker info --format '{{.Architecture}}' 2>/dev/null)"
case "$HOST_ARCH" in
    x86_64|amd64) ok "Host architecture: $HOST_ARCH" ;;
    *) warn "Host architecture is $HOST_ARCH, not amd64. The delivery image is built for amd64." ;;
esac

# The NVIDIA container runtime is what actually passes the GPU through. Without
# it, `--gpus all` is silently ignored and the container falls back to llvmpipe.
if [ "$GPU_KIND" != "nvidia" ]; then
    warn "SKIPPED nvidia runtime check (GPU path: $GPU_KIND)"
elif docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia; then
    ok "nvidia container runtime registered"
else
    bad "No 'nvidia' runtime in Docker. Install nvidia-container-toolkit, then restart Docker."
    bad "  Without it the container CANNOT see the GPU, whatever else is configured."
fi

# ---------------------------------------------------------------------
step "2. GPU visible inside a container"
# ---------------------------------------------------------------------
# Tested with the image's own base rather than a separate CUDA image, so this
# proves the GPU reaches THIS image, not just some image.
if [ "$GPU_KIND" != "nvidia" ]; then
    warn "SKIPPED nvidia-smi check (GPU path: $GPU_KIND)"
elif docker run --rm --gpus all "${SCARECROW_IMAGE:-scarecrow-sim:dev}" \
        nvidia-smi >/tmp/nvsmi.out 2>&1; then
    ok "nvidia-smi runs inside the container"
    sed 's/^/        /' /tmp/nvsmi.out | head -12
else
    bad "nvidia-smi failed inside the container. GPU is NOT passed through."
    sed 's/^/        /' /tmp/nvsmi.out | head -12 >&2
fi

case "$GPU_KIND" in
    wsl)
        if [ -e /dev/dxg ]; then ok "/dev/dxg present on the host (WSL2 GPU)"
        else bad "/dev/dxg missing. Run Docker inside the WSL2 distro, not Docker Desktop."; fi ;;
    dri)
        if [ -e /dev/dri ]; then ok "/dev/dri present on the host"
        else bad "/dev/dri missing -- no render node to pass through."; fi ;;
esac

# ---------------------------------------------------------------------
step "2b. Image self-test (nothing missing)"
# ---------------------------------------------------------------------
# Separates "the image is incomplete" from "this host has no GPU". Without it,
# a missing driver and an unexposed GPU produce the same symptom -- software
# rendering -- and you cannot tell which you are looking at.
if docker run --rm --entrypoint /opt/scarecrow/docker/self-test.sh \
        "${SCARECROW_IMAGE:-scarecrow-sim:dev}" >/tmp/selftest.out 2>&1; then
    ok "image self-test passed ($(grep -c '\[PASS\]' /tmp/selftest.out) checks)"
else
    bad "image self-test FAILED -- something is missing from the image itself:"
    grep '\[FAIL\]' /tmp/selftest.out | sed 's/^/      /' >&2
fi

# ---------------------------------------------------------------------
step "3. Renderer guard fails closed"
# ---------------------------------------------------------------------
# The guard must REFUSE to start on software rendering when REQUIRE_GPU=1.
# A guard that has never been seen failing is not a guard -- this asserts the
# failing direction explicitly, by forcing software rendering.
if docker run --rm -e REQUIRE_GPU=1 -e LIBGL_ALWAYS_SOFTWARE=1 \
        --entrypoint /opt/scarecrow/docker/check-renderer.sh \
        "${SCARECROW_IMAGE:-scarecrow-sim:dev}" >/dev/null 2>&1; then
    bad "check-renderer.sh ACCEPTED software rendering with REQUIRE_GPU=1."
    bad "  The guard is broken: a GPU-less run would silently fly on CPU."
else
    ok "check-renderer.sh correctly refuses software rendering when REQUIRE_GPU=1"
fi

# ---------------------------------------------------------------------
step "4. Start the product"
# ---------------------------------------------------------------------
docker compose --profile "$COMPOSE_PROFILE" up -d "$SERVICE" >/dev/null 2>&1 \
    && ok "container started" \
    || { bad "docker compose up failed"; docker compose --profile "$COMPOSE_PROFILE" logs --tail 40; exit 1; }

echo "  waiting for the UI (renderer check + Gazebo preflight take ~20-60s)..."
UI_UP=0
for _ in $(seq 1 60); do
    if curl -fs -m 3 "$WEBAPP/api/health" >/dev/null 2>&1; then UI_UP=1; break; fi
    if [ "$(docker compose --profile "$COMPOSE_PROFILE" ps -q "$SERVICE" | wc -l)" -eq 0 ]; then break; fi
    sleep 3
done

if [ "$UI_UP" = "1" ]; then
    ok "backend healthy at $WEBAPP/api/health"
else
    bad "UI never came up. Logs:"
    docker compose --profile "$COMPOSE_PROFILE" logs --tail 60 >&2
    exit 1
fi

# The renderer line the container itself reported. This is the real answer to
# "is it using the GPU", as opposed to "can it see one".
RENDERER="$(docker compose --profile "$COMPOSE_PROFILE" logs 2>/dev/null | grep -m1 '\[renderer\]')"
echo "  container reported: ${RENDERER:-<none>}"
case "$RENDERER" in
    *llvmpipe*|*softpipe*|*swrast*|*unknown*)
        if [ "$GPU_MODE" = "0" ]; then
            warn "software rendering (expected without a GPU; unusably slow for real missions)"
        else
            bad "Container is software rendering. Every GPU-rendered sensor would run on CPU."
        fi
        ;;
    "") warn "No renderer line in logs" ;;
    *) ok "hardware renderer in use" ;;
esac

if curl -fs -m 5 "$WEBAPP/" | grep -qi "<!doctype html"; then
    ok "UI served at $WEBAPP/"
else
    bad "UI not served at $WEBAPP/ -- the frontend build is missing from the image"
fi

# ---------------------------------------------------------------------
step "5. Launch the simulation through the UI's own API"
# ---------------------------------------------------------------------
# Deliberately via the REST API rather than a shell in the container: this is
# the exact path the Connect button takes, so it tests what the user does.
curl -fs -m 20 -X POST "$WEBAPP/api/sim/connect" \
     -H 'Content-Type: application/json' \
     -d '{"world":"hangar_small","headless":true,"camera":"fixed"}' >/dev/null 2>&1 \
    && ok "connect accepted" || bad "connect rejected"

echo "  waiting for PX4 + Gazebo..."
CONNECTED=0
for _ in $(seq 1 80); do
    if curl -fs -m 5 "$WEBAPP/api/sim/status" 2>/dev/null | grep -q '"connected": *true'; then
        CONNECTED=1; break
    fi
    sleep 3
done
[ "$CONNECTED" = "1" ] && ok "simulation connected" || bad "simulation never reached connected"

# PX4 must not rebuild -- the binary is baked into the image. A rebuild here
# means sim_service._skip_px4_build regressed, and the customer would sit
# through a compile (which would then fail, having none of the pinned flags).
#
# The launcher's stdout is piped to the backend, NOT to container stdout, so
# this has to come from /api/sim/log -- an earlier version grepped
# `docker compose logs` and reported a false negative on a correct run.
if curl -fs -m 5 "$WEBAPP/api/sim/log?since=0" 2>/dev/null | grep -q "Skipping PX4 build"; then
    ok "PX4 build skipped (binary from the image)"
else
    bad "PX4 was rebuilt on connect -- the launcher did not get --no-build"
fi

# ---------------------------------------------------------------------
step "6. Camera stream carries real frames"
# ---------------------------------------------------------------------
# Not a status code: HTTP 200 on a stream endpoint proved nothing when the
# WebRTC video was black. Pull real bytes and look for JPEG markers.
#
# /stream is an endless multipart response, so curl ALWAYS exits 28 (timeout)
# here -- that is success, not failure, and the partial body is the sample.
# Do not add `||` fallbacks on this: an earlier version fell back to fetching
# the HTML viewer page and then reported "no JPEG found" on a working stream.
curl -s --max-time 8 "$STREAM/stream" -o /tmp/frame.bin
FRAMES="$(grep -ac -- '--frame' /tmp/frame.bin 2>/dev/null || echo 0)"
if [ -s /tmp/frame.bin ] && head -c 4000 /tmp/frame.bin | grep -qa $'\xff\xd8\xff'; then
    ok "MJPEG frames served ($(wc -c </tmp/frame.bin | tr -d ' ') bytes, ~${FRAMES} frames in 8s)"
else
    bad "No JPEG data on $STREAM/stream -- the camera feed is not reaching the browser"
fi

# ---------------------------------------------------------------------
step "7. Fly: sensors through the flight-script path"
# ---------------------------------------------------------------------
# sensor_check exercises the whole subprocess chain (DetectionService ->
# python -> mavsdk -> PX4) and reports all four sensor groups, including the
# two gpu_lidar units that are the reason the GPU matters.
FLIGHT="$(curl -fs -m 30 -X POST "$WEBAPP/api/flight/start" \
    -H 'Content-Type: application/json' -d '{"script":"sensor_check.py","args":{}}' 2>/dev/null)"
if echo "$FLIGHT" | grep -q '"success" *: *true'; then
    ok "flight script started"
else
    bad "flight script would not start: $FLIGHT"
fi

echo "  waiting for sensor results..."
for _ in $(seq 1 40); do
    LOG="$(curl -fs -m 5 "$WEBAPP/api/flight/log" 2>/dev/null)"
    echo "$LOG" | grep -q "SENSOR DEMO RESULTS" && break
    sleep 3
done

for SENSOR in rangefinder lidar camera flow; do
    if echo "$LOG" | grep -q "\[OK *\] *$SENSOR"; then
        ok "sensor: $SENSOR"
    else
        bad "sensor FAILED or missing: $SENSOR"
    fi
done

# ---------------------------------------------------------------------
step "Summary"
# ---------------------------------------------------------------------
echo "  passed: $PASS   failed: $FAIL   warnings: $WARN"
echo
if [ "$FAIL" -eq 0 ]; then
    if [ "$GPU_MODE" = "0" ]; then
        echo "  Wiring OK, but this run had no GPU: rendering is UNVERIFIED."
        echo "  Re-run without --no-gpu on the delivery machine before handing over."
        exit 0
    fi
    echo "  READY. Open http://localhost:8000/ and use the system."
    exit 0
fi
echo "  NOT READY -- $FAIL check(s) failed above. Do not hand over until they pass." >&2
exit 1
