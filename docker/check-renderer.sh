#!/usr/bin/env bash
# Reports the active OpenGL renderer.
#
# WHY THIS EXISTS
# Every camera and lidar in this system is GPU-rendered: the mono camera, the
# optical-flow camera, the world's fixed camera, plus 2 gpu_lidar units
# (lidar_2d_v2 for wall following, tf_luna_up for the ceiling rangefinder).
# gpu_lidar does not raytrace on the CPU -- it renders depth through the
# graphics pipeline. So the renderer is a FLIGHT CONTROL concern, not a
# cosmetic one.
#
# A silent fallback to llvmpipe still "works", just slowly. That is the same
# fail-soft signature as the 2026-06-20 assimp bug: it hides for weeks and then
# surfaces as an unexplained regression. On the delivery hardware (ROG Strix,
# RTX 5090/5080 via WSL2) set REQUIRE_GPU=1 so the fallback is fatal instead.
#
# WHY EGL AND NOT glxinfo
# This container is headless: there is no X server and DISPLAY is unset, so
# `glxinfo -B` prints "unable to open display" and nothing else. The previous
# version of this script used glxinfo, so on the *delivery machine* it would
# have seen no renderer, called it "unknown", and with REQUIRE_GPU=1 refused to
# start -- meaning `docker compose --profile gpu up` would fail on a perfectly
# good RTX 5090. EGL's surfaceless platform needs no display and is the same
# path OGRE2 uses for offscreen rendering, so it reports what Gazebo will
# actually get.
set -uo pipefail

# eglinfo probes several platforms; only "Surfaceless" can work without a
# display, and the others print expected eglInitialize noise. Take the first
# renderer line after the Surfaceless section.
RENDERER="$(eglinfo -B 2>/dev/null \
    | awk '/Surfaceless platform:/{f=1} f && /OpenGL (core profile )?renderer:/{sub(/^[^:]*: */,""); print; exit}')"

# If a display does exist (run on a desktop, or with X forwarded), GLX is the
# more representative answer.
if [ -n "${DISPLAY:-}" ]; then
    GLX="$(glxinfo -B 2>/dev/null | grep -i 'OpenGL renderer' | cut -d: -f2- | sed 's/^ *//')"
    [ -n "$GLX" ] && RENDERER="$GLX"
fi

if [ -z "$RENDERER" ]; then
    RENDERER="unknown (no EGL or GLX renderer reported)"
fi

echo "[renderer] $RENDERER"

case "$RENDERER" in
    # "Microsoft Basic Render Driver" is the important one and the least
    # obvious. On Windows/WSL2 it arrives through the SAME Mesa d3d12 driver a
    # working GPU does, so anything that reasons "d3d12 means hardware" accepts
    # it -- and WSL falls back to it silently whenever the real GPU is not
    # exposed to the container. That is the single most likely way this ships
    # to someone and quietly renders every camera and lidar on the CPU.
    #
    # lavapipe is Vulkan's software driver, reached via zink.
    *llvmpipe*|*softpipe*|*swrast*|*lavapipe*|*"Software Rasterizer"* \
    |*"Microsoft Basic Render Driver"*|*SVGA3D*|unknown*)
        if [ "${REQUIRE_GPU:-0}" = "1" ]; then
            echo "[renderer] FATAL: REQUIRE_GPU=1 but renderer is software ($RENDERER)." >&2
            echo "[renderer] Every camera and gpu_lidar would render on CPU." >&2
            echo "" >&2
            echo "[renderer] Pick the compose profile that matches your GPU:" >&2
            echo "" >&2
            echo "[renderer]   NVIDIA (Windows/WSL2 or Linux):" >&2
            echo "[renderer]     docker compose --profile gpu up" >&2
            echo "[renderer]     Needs nvidia-container-toolkit, and Docker restarted" >&2
            echo "[renderer]     after installing it. If nvidia-smi works but this check" >&2
            echo "[renderer]     still fails, the cause is almost always capabilities:" >&2
            echo "[renderer]     the toolkit DEFAULTS to 'compute,utility', which gives" >&2
            echo "[renderer]     CUDA and nvidia-smi but NO OpenGL. 'graphics' is" >&2
            echo "[renderer]     required. Current: ${NVIDIA_DRIVER_CAPABILITIES:-<unset>}" >&2
            echo "" >&2
            echo "[renderer]   Any GPU on Windows (AMD, Intel, or NVIDIA) via WSL2:" >&2
            echo "[renderer]     docker compose --profile gpu-wsl up" >&2
            echo "[renderer]     Uses /dev/dxg and Mesa's d3d12 driver. Run Docker inside" >&2
            echo "[renderer]     the WSL2 distro; Docker Desktop only forwards NVIDIA." >&2
            echo "" >&2
            echo "[renderer]   AMD or Intel on native Linux:" >&2
            echo "[renderer]     docker compose --profile gpu-dri up" >&2
            echo "[renderer]     Passes /dev/dri through to Mesa (radeonsi / iris)." >&2
            echo "" >&2
            echo "[renderer] Diagnostics inside the container:" >&2
            echo "[renderer]   ls -l /dev/dri /dev/dxg   (is any GPU device visible?)" >&2
            echo "[renderer]   eglinfo -B                (what does EGL actually report?)" >&2
            exit 1
        fi
        echo "[renderer] WARNING: software rendering."
        echo "[renderer] Expected on macOS -- Docker Desktop exposes no GPU there."
        echo "[renderer] Sensors will be slow; fine for a smoke test, not for flying."
        ;;
    *)
        echo "[renderer] hardware acceleration detected"
        ;;
esac
