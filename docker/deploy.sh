#!/usr/bin/env bash
# Rebuild the Scarecrow image with local repo changes and restart the stack.
#
# WHY THIS EXISTS
# Worlds, models, scripts, scarecrow/, airframes, config and the webapp are
# COPYed into the image at build time. There are no bind mounts for them in
# docker-compose.yml, so editing worlds/*.sdf (or anything else under those
# trees) does NOTHING until you rebuild. A bare `docker compose up` keeps
# serving the old baked-in copy.
#
# PX4 itself is cloned and compiled in an earlier Docker layer. Changing a
# world only invalidates the later COPY layers, so a rebuild after the first
# full build is usually minutes, not the full PX4 compile.
#
#   bash docker/deploy.sh              # rebuild + restart compose (if it was up)
#   bash docker/deploy.sh --no-up      # rebuild only
#   bash docker/deploy.sh --no-cache   # passed through to build.sh
#
# Equivalent to: bash docker/build.sh && docker compose up -d
# (with a clean stop first when the previous container was running).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

NO_UP=0
BUILD_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --no-up) NO_UP=1 ;;
        -h|--help)
            sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) BUILD_ARGS+=("$arg") ;;
    esac
done

WAS_UP=0
if docker compose ps -q sim 2>/dev/null | grep -q .; then
    WAS_UP=1
fi
# One-off `sim.sh sim` containers also count as "was running" for messaging.
if [ "$WAS_UP" = "0" ] && docker compose ps -a -q sim 2>/dev/null | grep -q .; then
    WAS_UP=1
fi

echo "[deploy] Rebuilding scarecrow-sim:dev with local worlds/models/scripts/..."
echo "[deploy] (A new world SDF is invisible to Docker until this step.)"
echo
bash "$(dirname "$0")/build.sh" "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}"

if [ "$NO_UP" = "1" ]; then
    echo
    echo "[deploy] Image ready. Start when you want:"
    echo "[deploy]   docker compose up"
    echo "[deploy]   # or: bash docker/sim.sh sim --headless --fixed"
    exit 0
fi

echo
echo "[deploy] Stopping any previous scarecrow containers..."
bash "$(dirname "$0")/sim.sh" down 2>/dev/null || true
docker compose down --remove-orphans >/dev/null 2>&1 || true

echo "[deploy] Starting web console..."
docker compose up -d
echo
echo "[deploy] Ready → http://localhost:8000/"
echo "[deploy] New worlds appear under Connect once the UI lists them from"
echo "[deploy] /opt/scarecrow/worlds inside this rebuilt image."
if [ "$WAS_UP" = "0" ]; then
    echo "[deploy] (No prior container was running; started compose anyway."
    echo "[deploy]  Pass --no-up next time if you only wanted a rebuild.)"
fi
