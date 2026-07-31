#!/usr/bin/env bash
# Reports the active OpenGL renderer.
#
# WHY THIS EXISTS
# Every sensor in this system is GPU-rendered: 3 cameras plus 2 gpu_lidar
# (lidar_2d_v2 for wall following, tf_luna_up for the ceiling rangefinder).
# gpu_lidar does not raytrace on the CPU -- it renders depth through the
# graphics pipeline. So the renderer is a FLIGHT CONTROL concern, not a
# cosmetic one.
#
# A silent fallback to llvmpipe still "works", just slowly. That is the same
# fail-soft signature as the 2026-06-20 assimp bug: it hides for weeks and then
# surfaces as an unexplained regression. On the delivery hardware (ROG Strix,
# RTX 5090/5080 via WSL2) set REQUIRE_GPU=1 so the fallback is fatal instead.
set -uo pipefail

RENDERER="$(glxinfo -B 2>/dev/null | grep -i 'OpenGL renderer' | cut -d: -f2- | sed 's/^ *//')"

if [ -z "$RENDERER" ]; then
    RENDERER="unknown (glxinfo produced no output)"
fi

echo "[renderer] $RENDERER"

case "$RENDERER" in
    *llvmpipe*|*softpipe*|*swrast*|unknown*)
        if [ "${REQUIRE_GPU:-0}" = "1" ]; then
            echo "[renderer] FATAL: REQUIRE_GPU=1 but renderer is software ($RENDERER)." >&2
            echo "[renderer] All 5 sensors (3 cameras + 2 gpu_lidar) would run on CPU." >&2
            echo "[renderer] On Windows/WSL2 check: nvidia-container-toolkit installed," >&2
            echo "[renderer] container run with --gpus all, and host NVIDIA driver current." >&2
            exit 1
        fi
        echo "[renderer] WARNING: software rendering (llvmpipe)."
        echo "[renderer] Expected on macOS -- Docker Desktop exposes no GPU there."
        echo "[renderer] Sensors will be slow; acceptable for hangar_small, not for complex worlds."
        ;;
    *)
        echo "[renderer] hardware acceleration detected"
        ;;
esac
