#!/usr/bin/env bash
# Build the Scarecrow delivery image with the pinned toolchain versions.
#
# USE THIS INSTEAD OF `docker compose build`.
#
# The base image digest and Gazebo version live in docker/versions.env, which
# Compose does not read on its own (it only auto-loads a root `.env`, and that
# path is gitignored so the pins could not be committed there). Building
# without them produces `FROM ubuntu@` and a cryptic "invalid reference
# format".
#
# Customers never run this -- they `docker compose up` against a prebuilt
# image. This is the maintainer path, for deliberately bumping a pin.
#
#   bash docker/build.sh                 # build for this machine's architecture
#   bash docker/build.sh --no-cache      # extra args are passed through
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [ ! -f docker/versions.env ]; then
    echo "FATAL: docker/versions.env not found -- cannot resolve the pinned versions." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1091
. docker/versions.env
set +a

: "${UBUNTU_DIGEST:?UBUNTU_DIGEST missing from docker/versions.env}"
: "${GZ_VERSION:?GZ_VERSION missing from docker/versions.env}"

echo "[build] UBUNTU_DIGEST=$UBUNTU_DIGEST"
echo "[build] GZ_VERSION=$GZ_VERSION"
echo "[build] arch=$(docker info --format '{{.Architecture}}' 2>/dev/null)"
echo

# The delivery target is amd64. Emulating it on an arm64 Mac takes hours, so
# say so rather than letting someone start a build that will not finish.
ARCH="$(docker info --format '{{.Architecture}}' 2>/dev/null || echo unknown)"
case "$ARCH" in
    aarch64|arm64)
        echo "[build] NOTE: building an arm64 image. This validates the Dockerfile," >&2
        echo "[build] but the customer machines are amd64 -- that image must be built" >&2
        echo "[build] ON an amd64 host. Cross-building it here would take hours." >&2
        echo >&2
        ;;
esac

docker compose build "$@"
STATUS=$?

# Reclaim what the rebuild orphaned.
#
# Every rebuild retags scarecrow-sim:dev and leaves the previous image
# untagged. At ~13GB each these are invisible in `docker images` (they show as
# <none>) and add up fast -- six rebuilds during one session had consumed
# 18.6GB of otherwise unreachable disk.
#
# Only unreferenced data is removed: `image prune` touches dangling images
# only, never a tagged one, and `builder prune` drops cache entries no current
# image depends on. The next incremental build is unaffected.
# Work out which GPU this machine has and write it to .env, so the customer's
# next command is a bare `docker compose up` rather than a profile they have to
# choose correctly. Picking wrong is silent: the container simply gets no GPU
# and Gazebo renders on the CPU.
if [ "$STATUS" -eq 0 ]; then
    echo
    bash "$(dirname "$0")/detect-gpu.sh" || true
fi

if [ "$STATUS" -eq 0 ]; then
    echo
    echo "[build] Reclaiming orphaned images and build cache..."
    docker image prune -f 2>/dev/null | tail -1
    docker builder prune -f 2>/dev/null | tail -1
    echo
    docker system df
fi

exit "$STATUS"
