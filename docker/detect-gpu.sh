#!/usr/bin/env bash
# Work out which GPU path this machine has, and let `docker compose up` use it.
#
# WHY THIS EXISTS
# Compose YAML has no conditionals, and the three GPU paths need *different
# devices* -- an NVIDIA runtime reservation, /dev/dxg for WSL2, /dev/dri for
# native Linux. Listing all three in one service does not degrade gracefully:
# if /dev/dxg is absent, `docker compose up` fails outright rather than
# skipping it. So the choice has to be made outside Compose, which is what
# profiles are for.
#
# That left the customer picking a profile by hand, and picking wrong is the
# most expensive mistake available here: --profile gpu on an AMD laptop
# attaches no GPU, nothing errors, and Gazebo quietly renders on the CPU.
#
# Compose reads COMPOSE_FILE from .env, so writing the answer there once makes
# the bare `docker compose up` correct on any machine. The overlays modify the
# `sim` service in place rather than adding a second one, so there is never a
# second container competing for the published ports.
#
#   bash docker/detect-gpu.sh            # detect, write .env, explain
#   bash docker/detect-gpu.sh --print    # print the COMPOSE_FILE, write nothing
#
# .env is gitignored: it describes this machine, not the project.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
PRINT_ONLY=0
[ "${1:-}" = "--print" ] && PRINT_ONLY=1

# On native Linux, NVIDIA toolkit OpenGL works. On WSL2 it does not: CUDA
# reaches the container (nvidia-smi works) but EGL stays on llvmpipe. Gazebo
# needs Mesa d3d12 via /dev/dxg. Hybrid NVIDIA+Intel laptops also need
# MESA_D3D12_DEFAULT_ADAPTER_NAME or Mesa picks the iGPU.
has_nvidia_runtime() {
    docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q nvidia
}

detect_gpu_kind() {
    if [ -e /dev/dxg ] && has_nvidia_runtime; then
        echo "nvidia-wsl"
    elif has_nvidia_runtime; then
        echo "nvidia"
    elif [ -e /dev/dxg ]; then
        echo "wsl"
    elif [ -e /dev/dri ]; then
        echo "dri"
    else
        echo "none"
    fi
}

GPU_KIND="$(detect_gpu_kind)"
ADAPTER_NAME=""

case "$GPU_KIND" in
    nvidia-wsl)
        OVERLAY="docker/compose.gpu.yml:docker/compose.gpu-wsl.yml"
        ADAPTER_NAME="NVIDIA"
        ;;
    nvidia) OVERLAY="docker/compose.gpu.yml"     ;;
    wsl)    OVERLAY="docker/compose.gpu-wsl.yml" ;;
    dri)    OVERLAY="docker/compose.gpu-dri.yml" ;;
    none)   OVERLAY=""                           ;;
esac

COMPOSE_FILE_VALUE="docker-compose.yml"
[ -n "$OVERLAY" ] && COMPOSE_FILE_VALUE="docker-compose.yml:$OVERLAY"

if [ "$PRINT_ONLY" = "1" ]; then
    echo "$COMPOSE_FILE_VALUE"
    exit 0
fi

# Preserve any other settings the user keeps in .env; replace only our lines.
TMP="$(mktemp)"
if [ -f "$ENV_FILE" ]; then
    grep -vE '^(COMPOSE_FILE|COMPOSE_PROFILES|MESA_D3D12_DEFAULT_ADAPTER_NAME)=' "$ENV_FILE" > "$TMP" 2>/dev/null || true
fi
echo "COMPOSE_FILE=$COMPOSE_FILE_VALUE" >> "$TMP"
if [ -n "$ADAPTER_NAME" ]; then
    echo "MESA_D3D12_DEFAULT_ADAPTER_NAME=$ADAPTER_NAME" >> "$TMP"
fi
mv "$TMP" "$ENV_FILE"

echo "[detect-gpu] GPU path: $GPU_KIND"
case "$GPU_KIND" in
    nvidia-wsl)
        echo "[detect-gpu] WSL2 + NVIDIA toolkit: CUDA via nvidia, OpenGL via /dev/dxg."
        echo "[detect-gpu] Wrote both overlays and MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA"
        echo "[detect-gpu] (without the adapter pin, Mesa often picks the Intel iGPU)."
        ;;
    nvidia)
        echo "[detect-gpu] NVIDIA container runtime found."
        echo "[detect-gpu] Wrote the NVIDIA overlay -- 'docker compose up' will use it."
        ;;
    wsl)
        echo "[detect-gpu] /dev/dxg present: a GPU is exposed through WSL2."
        echo "[detect-gpu] Wrote the WSL2 overlay -- 'docker compose up' will use it."
        echo "[detect-gpu] YOLO runs on the CPU unless this is an NVIDIA card;"
        echo "[detect-gpu] PyTorch has no backend for AMD or Intel here."
        ;;
    dri)
        echo "[detect-gpu] /dev/dri present: AMD or Intel on native Linux."
        echo "[detect-gpu] Wrote the /dev/dri overlay -- 'docker compose up' will use it."
        ;;
    none)
        echo "[detect-gpu] No GPU device found. No overlay written --" >&2
        echo "[detect-gpu] 'docker compose up' will run on the CPU." >&2
        echo "[detect-gpu] That works, but it is too slow to fly a full mission." >&2
        echo "" >&2
        echo "[detect-gpu] If this machine HAS a GPU, one of these is why:" >&2
        echo "[detect-gpu]   - Windows + AMD/Intel: Docker Desktop forwards only NVIDIA" >&2
        echo "[detect-gpu]     devices, so /dev/dxg never appears. Install Docker Engine" >&2
        echo "[detect-gpu]     natively inside the WSL2 distro instead." >&2
        echo "[detect-gpu]   - Windows + NVIDIA: install the NVIDIA Container Toolkit." >&2
        echo "[detect-gpu]   - Native Linux: check you are in the 'render' and 'video'" >&2
        echo "[detect-gpu]     groups, so /dev/dri is readable." >&2
        ;;
esac
