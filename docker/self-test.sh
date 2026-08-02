#!/usr/bin/env bash
# In-image self-test: everything that can be proven WITHOUT the target GPU.
#
#   docker run --rm scarecrow-sim:dev /opt/scarecrow/docker/self-test.sh
#
# WHY THIS EXISTS
# The image is built and validated on an arm64 Mac with no NVIDIA, no AMD, no
# Intel GPU and no WSL. That leaves two very different risks for the machine it
# actually ships to:
#
#   1. MISSING DEPENDENCIES -- a driver, shared library, plugin or Python module
#      that simply is not in the image. This is fully provable here, and it is
#      the failure that would otherwise strand someone on a machine with no way
#      to diagnose it.
#
#   2. NO HARDWARE -- the host does not expose a GPU to the container. Not
#      provable here, by definition. docker/verify-delivery.sh covers it on the
#      target machine.
#
# This script closes (1) completely, and closes as much of (2) as is possible
# by feeding check-renderer.sh recorded output from real NVIDIA / AMD / Intel /
# WSL systems and asserting it classifies each one correctly. That means the
# renderer guard is tested against hardware it has never seen.
#
# Exit 0 = nothing is missing from the image. It does NOT mean the GPU works.
set -uo pipefail

PASS=0
FAIL=0
WARN=0
ok()   { echo "  [PASS] $*"; PASS=$((PASS + 1)); }
bad()  { echo "  [FAIL] $*" >&2; FAIL=$((FAIL + 1)); }
# For things that degrade the image without breaking it. Counted and reported
# separately so a slow-but-working image is not mistaken for a clean one.
warn() { echo "  [WARN] $*" >&2; WARN=$((WARN + 1)); }
step() { echo; echo "=== $* ==="; }

ROOT=/opt/scarecrow

# ---------------------------------------------------------------------
step "1. Mesa drivers for every GPU vendor the delivery may meet"
# ---------------------------------------------------------------------
# Present AND loadable: a driver whose own shared-library deps are unresolved
# fails at dlopen with a message Mesa swallows, and the only symptom is a
# silent fall back to llvmpipe -- indistinguishable from having no GPU.
check_driver() {
    local drv="$1" why="$2"
    local so
    so="$(ls /usr/lib/*/dri/${drv}_dri.so 2>/dev/null | head -1)"
    if [ -z "$so" ]; then
        bad "$drv driver MISSING ($why)"
        return
    fi
    local missing
    missing="$(ldd "$so" 2>/dev/null | grep 'not found' | awk '{print $1}' | tr '\n' ' ')"
    if [ -n "$missing" ]; then
        bad "$drv present but unresolved libs: $missing"
    else
        ok "$drv ($why)"
    fi
}

check_driver d3d12    "Windows/WSL2 - any vendor, incl. AMD and Intel"
check_driver radeonsi "AMD on native Linux"
check_driver iris     "Intel on native Linux"
check_driver zink     "Vulkan fallback"
check_driver swrast   "software fallback"

# ---------------------------------------------------------------------
step "2. EGL / GL stack"
# ---------------------------------------------------------------------
# The renderer probe and OGRE2's offscreen rendering both go through EGL.
for lib in libEGL.so.1 libGL.so.1 libGLdispatch.so.0 libOpenGL.so.0; do
    if ldconfig -p 2>/dev/null | grep -q "$lib"; then
        ok "$lib"
    else
        bad "$lib MISSING -- EGL/GL cannot initialise"
    fi
done

for tool in eglinfo glxinfo; do
    command -v "$tool" >/dev/null 2>&1 && ok "$tool available" || bad "$tool MISSING"
done

# The NVIDIA vendor JSON is injected by nvidia-container-toolkit at RUNTIME, so
# its absence here is correct and expected. Mesa's must be baked in.
[ -f /usr/share/glvnd/egl_vendor.d/50_mesa.json ] \
    && ok "Mesa EGL vendor config present" \
    || bad "50_mesa.json MISSING -- EGL cannot find the Mesa driver"

# ---------------------------------------------------------------------
step "3. Renderer guard vs. real hardware strings it has never seen"
# ---------------------------------------------------------------------
# check-renderer.sh parses `eglinfo -B`. Here it is fed recorded output from
# real machines, so the parser and the software/hardware classification are
# tested against NVIDIA, AMD, Intel and WSL formats on a Mac with none of them.
MOCKDIR="$(mktemp -d)"
mock_renderer() {
    cat > "$MOCKDIR/eglinfo" <<EOF
#!/bin/sh
cat <<'INNER'
GBM platform:
eglinfo: eglInitialize failed

Surfaceless platform:
EGL API version: 1.5
EGL vendor string: $2
OpenGL core profile renderer: $1
OpenGL core profile version: 4.6
INNER
EOF
    chmod +x "$MOCKDIR/eglinfo"
}

# expect_pass: renderer must be treated as HARDWARE (exit 0 with REQUIRE_GPU=1)
expect_pass() {
    mock_renderer "$1" "${3:-Mesa Project}"
    if PATH="$MOCKDIR:$PATH" REQUIRE_GPU=1 DISPLAY= "$ROOT/docker/check-renderer.sh" >/dev/null 2>&1; then
        ok "recognised as hardware: $2"
    else
        bad "REJECTED a real GPU: $2  ('$1')"
    fi
}

# expect_fail: renderer must be treated as SOFTWARE (exit 1 with REQUIRE_GPU=1)
expect_fail() {
    mock_renderer "$1" "${3:-Mesa Project}"
    if PATH="$MOCKDIR:$PATH" REQUIRE_GPU=1 DISPLAY= "$ROOT/docker/check-renderer.sh" >/dev/null 2>&1; then
        bad "ACCEPTED software rendering: $2  ('$1')"
    else
        ok "rejected as software: $2"
    fi
}

expect_pass "NVIDIA GeForce RTX 5090/PCIe/SSE2" "NVIDIA RTX 5090 (delivery laptop)" "NVIDIA"
expect_pass "NVIDIA GeForce RTX 5080/PCIe/SSE2" "NVIDIA RTX 5080 (delivery laptop)" "NVIDIA"
expect_pass "AMD Radeon RX 7900 XTX (radeonsi, navi31, LLVM 17.0.6, DRM 3.54)" "AMD discrete on Linux"
expect_pass "AMD Radeon 780M Graphics (radeonsi, gfx1103_r1, LLVM 17.0.6)" "AMD integrated on Linux"
expect_pass "Mesa Intel(R) Arc(tm) A770 Graphics (DG2)" "Intel Arc on Linux"
expect_pass "Mesa Intel(R) UHD Graphics 620 (KBL GT2)" "Intel integrated on Linux"
expect_pass "D3D12 (NVIDIA GeForce RTX 4060 Laptop GPU)" "NVIDIA via WSL2"
expect_pass "D3D12 (AMD Radeon(TM) 780M Graphics)" "AMD via WSL2 (student laptop)"
expect_pass "D3D12 (Intel(R) Iris(R) Xe Graphics)" "Intel via WSL2 (student laptop)"

expect_fail "llvmpipe (LLVM 20.1.2, 128 bits)" "Mesa software rasteriser"
expect_fail "softpipe" "Mesa softpipe"
expect_fail "SVGA3D; build: RELEASE;  LLVM;" "VMware software"
# WSL falls back to Microsoft's software adapter when no real GPU is exposed.
# It arrives through the SAME d3d12 driver as a working GPU, so a naive
# "D3D12 means hardware" test would pass it and fly the whole sim on the CPU.
expect_fail "D3D12 (Microsoft Basic Render Driver)" "WSL software adapter"
rm -rf "$MOCKDIR"

# ---------------------------------------------------------------------
step "4. Gazebo rendering plugins resolve"
# ---------------------------------------------------------------------
# gpu_lidar and every camera render through ogre2. A missing plugin dependency
# here is the 2026-06-20 assimp failure all over again.
OGRE_PLUGIN="$(find / -name 'libgz-rendering*-ogre2.so*' -not -path '*/proc/*' 2>/dev/null | head -1)"
if [ -n "$OGRE_PLUGIN" ]; then
    MISSING="$(ldd "$OGRE_PLUGIN" 2>/dev/null | grep 'not found' | awk '{print $1}' | tr '\n' ' ')"
    [ -z "$MISSING" ] && ok "ogre2 render plugin resolves" || bad "ogre2 plugin unresolved libs: $MISSING"
else
    bad "ogre2 render plugin NOT FOUND -- cameras and gpu_lidar cannot render"
fi

if ldconfig -p 2>/dev/null | grep -q libassimp; then
    ok "libassimp present (mesh loader; its absence broke everything on 2026-06-20)"
else
    bad "libassimp MISSING -- Gazebo cannot load meshes"
fi

# ---------------------------------------------------------------------
step "5. PX4 binary"
# ---------------------------------------------------------------------
PX4_BIN="$ROOT/px4/build/px4_sitl_default/bin/px4"
if [ -x "$PX4_BIN" ]; then
    MISSING="$(ldd "$PX4_BIN" 2>/dev/null | grep 'not found' | awk '{print $1}' | tr '\n' ' ')"
    [ -z "$MISSING" ] && ok "px4 binary links cleanly" || bad "px4 unresolved libs: $MISSING"
else
    bad "px4 binary missing -- the webapp would try to rebuild it on Connect"
fi

find "$ROOT/.venv" -name 'mavsdk_server*' -type f 2>/dev/null | head -1 | grep -q . \
    && ok "bundled mavsdk_server present" \
    || bad "no mavsdk_server -- no flight script can connect to PX4"

# ---------------------------------------------------------------------
step "6. Python imports the flight path needs"
# ---------------------------------------------------------------------
# These are imported lazily INSIDE functions, so a missing one does not fail at
# startup -- it fails mid-flight, which is exactly the late failure this image
# exists to prevent.
for mod in mavsdk numpy cv2 matplotlib torch torchvision ultralytics aiohttp av fastapi uvicorn; do
    if python3 -c "import $mod" >/dev/null 2>&1; then
        ok "import $mod"
    else
        bad "import $mod FAILED"
    fi
done

python3 -c "import scarecrow" >/dev/null 2>&1 \
    && ok "import scarecrow (PYTHONPATH correct)" \
    || bad "import scarecrow FAILED -- every flight script would die on its first import"

# The sensors fall back to `gz topic -e -n 1` polling without these, which is a
# fork+exec per lidar scan and per camera frame. That fallback still flies, so
# nothing here crashes -- the image just runs the simulator several times
# slower than it should, silently. Warn rather than fail for exactly that
# reason: a degraded image is not a broken one.
# Which device YOLO will actually use here. CPU inference measured 200ms/frame
# versus 41ms on an accelerator, and that load competes with the simulator for
# cores. Not a failure: AMD and Intel hosts have no torch backend at all, so
# CPU is the correct and only answer there.
YOLO_DEV=$(SCARECROW_YOLO_DEVICE= python3 -c \
    "from scarecrow.detection.yolo import select_inference_device as s; print(s())" \
    2>/dev/null || echo "unknown")
case "$YOLO_DEV" in
    cuda*) ok "YOLO inference device: $YOLO_DEV (GPU accelerated)" ;;
    mps)   ok "YOLO inference device: mps (GPU accelerated)" ;;
    cpu)   warn "YOLO inference device: cpu -- detection is several times slower there and competes with the simulator for cores. Expected on AMD/Intel hosts; on an NVIDIA host it means CUDA is not reaching the container (check nvidia-container-toolkit, and that detect-gpu.sh chose the NVIDIA overlay)" ;;
    *)     bad  "YOLO device could not be determined -- detection may not run at all" ;;
esac

if python3 -c "from gz.transport13 import Node" >/dev/null 2>&1; then
    ok "gz-transport python bindings present (sensors subscribe in-process)"
else
    warn "gz-transport python bindings MISSING -- sensors will fall back to per-sample CLI polling and the sim will run slow"
fi

# ---------------------------------------------------------------------
step "7. Webapp assets"
# ---------------------------------------------------------------------
[ -f "$ROOT/webapp/frontend/build/index.html" ] \
    && ok "frontend build present (backend can serve the UI)" \
    || bad "frontend build MISSING -- :8000 would serve nothing"

python3 -c "
import sys; sys.path.insert(0, '$ROOT/webapp/backend')
import app
assert app.app
" >/dev/null 2>&1 && ok "backend imports" || bad "backend failed to import"

# ---------------------------------------------------------------------
step "Summary"
# ---------------------------------------------------------------------
echo "  passed: $PASS   failed: $FAIL   warnings: $WARN"
echo
if [ "$WARN" -gt 0 ]; then
    echo "  $WARN warning(s) above: the image works but runs slower than it should."
    echo
fi
if [ "$FAIL" -eq 0 ]; then
    echo "  Nothing is missing from the image, and the renderer guard classifies"
    echo "  NVIDIA / AMD / Intel / WSL correctly."
    echo
    echo "  This does NOT prove the GPU works on the target machine -- only that"
    echo "  no dependency is absent. Run docker/verify-delivery.sh there."
    exit 0
fi
echo "  $FAIL check(s) failed -- the image is incomplete. Fix before shipping." >&2
exit 1
