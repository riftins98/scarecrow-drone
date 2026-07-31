#!/usr/bin/env bash
# Container entrypoint.
#
# This deliberately does NOT reimplement any launch logic. It sets up the
# environment and execs the repo's own launch_with_stream.sh, so the container
# cannot drift from the native developer path.
set -euo pipefail

WORLD="${WORLD:-hangar_small}"
CAMERA="${CAMERA:-fixed}"
STREAM_PORT="${STREAM_PORT:-8080}"

echo "[entrypoint] world=$WORLD camera=$CAMERA port=$STREAM_PORT"

WORLD_SDF="/opt/scarecrow/worlds/${WORLD}.sdf"
if [ ! -f "$WORLD_SDF" ]; then
    echo "[entrypoint] FATAL: world not found: $WORLD_SDF" >&2
    echo "[entrypoint] Available worlds:" >&2
    ls -1 /opt/scarecrow/worlds/*.sdf 2>/dev/null | xargs -n1 basename | sed 's/^/  /' >&2
    exit 1
fi

/opt/scarecrow/docker/check-renderer.sh

# Source env.sh BEFORE the preflight. It sets GZ_SIM_RESOURCE_PATH, without
# which Gazebo cannot resolve model:// URIs and the preflight fails with
# "Unable to find uri[model://...]". launch_with_stream.sh sources this itself,
# but that happens after the preflight runs.
# shellcheck disable=SC1091
source /opt/scarecrow/scripts/shell/env.sh >/dev/null 2>&1 || {
    echo "[entrypoint] FATAL: could not source scripts/shell/env.sh" >&2
    exit 1
}
echo "[entrypoint] GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH"

# Preflight: prove Gazebo can actually START before handing off to PX4.
# Without this, a broken graphics stack surfaces as PX4 retrying
# "Waiting for Gazebo world..." 29 times and then "Timed out waiting for Gazebo
# world" -- which says nothing about the real cause. Observed on the developer
# Mac 2026-07-31 with a missing libassimp.
# Set SKIP_PREFLIGHT=1 to save ~20s once the image is trusted.
if [ "${SKIP_PREFLIGHT:-0}" != "1" ]; then
    echo "[entrypoint] Gazebo preflight..."
    if ! timeout 90 /usr/local/bin/smoke-test.sh "$WORLD_SDF"; then
        echo "[entrypoint] FATAL: Gazebo preflight failed - refusing to start PX4." >&2
        echo "[entrypoint] PX4 would only report a useless 'Timed out waiting for Gazebo world'." >&2
        exit 1
    fi
fi

# Gazebo needs a resolvable IP; loopback breaks discovery.
GZ_IP="$(hostname -i 2>/dev/null | awk '{print $1}')"
export GZ_IP
export GZ_PARTITION="${GZ_PARTITION:-px4}"
echo "[entrypoint] GZ_IP=$GZ_IP GZ_PARTITION=$GZ_PARTITION"

cd /opt/scarecrow

# --no-build is what makes startup fast: PX4 is already compiled into the image.
exec ./scripts/shell/launch_with_stream.sh "$WORLD" \
    --headless \
    --"$CAMERA" \
    --no-open \
    --no-build \
    --port "$STREAM_PORT"
