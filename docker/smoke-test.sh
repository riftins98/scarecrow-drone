#!/usr/bin/env bash
# In-image assertions. Every check fails loudly; none of them warn.
#
# CRITICAL LESSON (2026-07-31): `gz sim --versions` is NOT a health check.
# On the developer Mac it returned "8.14.0" successfully while `gz sim -r -s <world>`
# could not start at all, because the CLI plugin libgz-sim8-gz -> gz-common5-graphics
# -> libassimp.6 was missing. PX4 gates on --versions, so startup proceeded and then
# died with "Timed out waiting for Gazebo world" after 29 retries.
#
# Only actually STARTING a server proves Gazebo works. Checks 1-3 are necessary but
# nowhere near sufficient. Check 4 is the one that matters. Do not weaken it.
set -euo pipefail

fail() { echo "SMOKE FAIL: $*" >&2; exit 1; }

# --- 1. Gazebo CLI responds. Necessary, NOT sufficient. See header. ---
gz sim --versions >/dev/null 2>&1 || fail "gz sim --versions did not succeed"
echo "  gz sim: $(gz sim --versions 2>/dev/null | head -1)"

# --- 2. assimp present. Direct guard for the Jun 20 regression. ---
ldconfig -p 2>/dev/null | grep -q libassimp \
  || fail "libassimp not found — Gazebo will fail to start"
echo "  libassimp: present"

# --- 3. The gz CLI plugin resolves all its shared libraries. ---
GZ_CLI_LIB="$(find /usr/lib -name 'libgz-sim*-gz.so*' 2>/dev/null | head -1)"
if [ -n "$GZ_CLI_LIB" ]; then
    if ldd "$GZ_CLI_LIB" 2>/dev/null | grep -q 'not found'; then
        ldd "$GZ_CLI_LIB" | grep 'not found' >&2
        fail "gz CLI plugin has unresolved libraries"
    fi
    echo "  gz CLI plugin libs: all resolved"
fi

# --- 4. THE decisive check: start a headless server, confirm it serves a world. ---
WORLD_SDF="${1:-/opt/scarecrow/worlds/hangar_small.sdf}"
[ -f "$WORLD_SDF" ] || fail "world file not found: $WORLD_SDF"
echo "  starting gz server on $(basename "$WORLD_SDF") ..."

gz sim --headless-rendering -s -r -v1 "$WORLD_SDF" >/tmp/gz_smoke.log 2>&1 &
GZ_PID=$!

WORLD_UP=0
for _ in $(seq 1 40); do
    if gz topic -l 2>/dev/null | grep -q '/clock'; then WORLD_UP=1; break; fi
    kill -0 "$GZ_PID" 2>/dev/null || break
    sleep 1
done

kill "$GZ_PID" 2>/dev/null || true
wait "$GZ_PID" 2>/dev/null || true

if [ "$WORLD_UP" -ne 1 ]; then
    echo "--- gz server output ---" >&2
    cat /tmp/gz_smoke.log >&2 || true
    fail "gz server never published /clock — Gazebo cannot start"
fi
echo "  gz server started and served /clock: ok"

echo "SMOKE OK"
