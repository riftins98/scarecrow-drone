#!/usr/bin/env bash
# Assert the PX4 build linked the pixi environment's Gazebo, not Homebrew's.
#
# WHY THIS MATTERS
# Homebrew ships the SAME gz-transport13 13.5.0 that conda-forge does. If
# CMake picks Homebrew's copy, the build succeeds, the sim runs, and the
# "reproducible environment" proves nothing -- it is silently depending on
# whatever the developer happens to have installed. The pixi build task passes
# -DCMAKE_IGNORE_PREFIX_PATH=/opt/homebrew to prevent that; this script checks
# it actually worked.
#
# Run via:  pixi run verify-isolation
#
# NOTE: this lives in a script rather than inline in pixi.toml because pixi
# executes tasks with deno_task_shell, which does not support `if` and fails
# with "Unsupported reserved word".
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="$REPO_ROOT/px4/build/px4_sitl_default/bin/px4"

if [ ! -x "$BIN" ]; then
    echo "SKIP: no px4 binary at $BIN -- run 'pixi run build' first" >&2
    exit 2
fi

# `otool -L` prints the inspected file's own path as its first line, so that
# line must be skipped -- otherwise a repo checked out under a path containing
# "/opt/homebrew" would false-positive, and a binary whose only match IS the
# header would look like a failure.
LIBS=$(otool -L "$BIN" 2>/dev/null | tail -n +2)

if printf '%s\n' "$LIBS" | grep -q /opt/homebrew; then
    echo "FAIL: px4 binary links Homebrew libraries:" >&2
    printf '%s\n' "$LIBS" | grep /opt/homebrew >&2
    echo "" >&2
    echo "The build picked up /opt/homebrew instead of the pixi environment." >&2
    echo "Check that 'pixi run build' still passes -DCMAKE_IGNORE_PREFIX_PATH." >&2
    exit 1
fi

RPATHS=$(printf '%s\n' "$LIBS" | grep -c "@rpath")
echo "OK: no Homebrew references in px4 binary (${RPATHS} @rpath entries resolve into .pixi)"
