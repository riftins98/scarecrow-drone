#!/bin/bash
# Shared environment for all scarecrow-drone scripts.
# Source this file: source scripts/env.sh
#
# CHANGELOG
#   2026-05-02 — On WSL2 auto-set SCARECROW_TAKEOFF_TIMEOUT=300 because the sim
#                runs at ~10% real-time-factor under WSL2 lockstep. Mac/native
#                Linux unchanged (default 30s takeoff timeout).
#                NOLOCKSTEP NOTE: launch.sh supports SCARECROW_NOLOCKSTEP=1 as
#                an opt-in build-target switch for px4_sitl_nolockstep, but it
#                is NOT auto-enabled — empirical test on 2026-05-02 showed that
#                with nolockstep PX4 sensors (mag/baro/accel) timeout against
#                the gz simulator clock and the EKF never gets data. Lockstep+
#                timeout is the working configuration.
#                GZ_SIM_SYSTEM_PLUGIN_PATH still routes to the right build dir
#                if a user manually sets SCARECROW_NOLOCKSTEP=1.
#                Backup at scripts/shell/env.sh.bak. Revert: `mv env.sh.bak env.sh`.

# Resolve repo root (works from any subdirectory)
export SCARECROW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PX4_DIR="$SCARECROW_DIR/px4"

# Gazebo resource paths (includes our custom models and worlds).
# Note: GZ_SIM_SYSTEM_PLUGIN_PATH is set lower down — it depends on whether
# nolockstep is active (different build dir name).
export GZ_SIM_RESOURCE_PATH="$SCARECROW_DIR/models:$SCARECROW_DIR/worlds:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds"
export GZ_SIM_SERVER_CONFIG_PATH="$PX4_DIR/src/modules/simulation/gz_bridge/server.config"

# Network — Gazebo needs real IP (not 127.0.0.1, loopback breaks multicast)
if command -v ipconfig &>/dev/null; then
    export GZ_IP="$(ipconfig getifaddr en0 2>/dev/null)"
elif command -v hostname &>/dev/null; then
    export GZ_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
export GZ_PARTITION=px4

# Disable PX4's automatic camera follow — keeps Gazebo view controls (scroll, orbit, pan) active
export PX4_GZ_NO_FOLLOW=1

# macOS SDK workaround (needed if system SDK symlink is broken)
if [[ "$(uname)" == "Darwin" ]]; then
    # Find the latest macOS SDK automatically
    if [ -d "/Library/Developer/CommandLineTools/SDKs" ]; then
        LATEST_SDK=$(ls -d /Library/Developer/CommandLineTools/SDKs/MacOSX*.sdk 2>/dev/null | sort -V | tail -1)
        if [ -n "$LATEST_SDK" ]; then
            export SDKROOT="$LATEST_SDK"
            export CXXFLAGS="-cxx-isystem ${SDKROOT}/usr/include/c++/v1 -isysroot ${SDKROOT}"
        fi
    fi
    # Qt5 for Gazebo GUI (homebrew path)
    if [ -d "$(brew --prefix 2>/dev/null)/opt/qt@5" ]; then
        export CMAKE_PREFIX_PATH="$(brew --prefix)/opt/qt@5:$CMAKE_PREFIX_PATH"
    fi
fi

# WSL2 detection — bump takeoff timeout because sim runs at ~10% RTF on WSL2.
# Lockstep is required (without it, PX4 sensors timeout against the gz clock
# and the EKF never gets data — verified empirically 2026-05-02). The timeout
# bump is therefore the only fix.
# Mac/native-Linux unchanged.
if [ -z "${SCARECROW_TAKEOFF_TIMEOUT:-}" ] && [ -r /proc/version ] \
        && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
    export SCARECROW_TAKEOFF_TIMEOUT=300
fi

# Pick the right PX4 build dir for the gz plugins path. nolockstep builds
# go into build/px4_sitl_nolockstep instead of build/px4_sitl_default.
if [ "${SCARECROW_NOLOCKSTEP:-0}" = "1" ]; then
    _PX4_BUILD_DIR_NAME="px4_sitl_nolockstep"
else
    _PX4_BUILD_DIR_NAME="px4_sitl_default"
fi
export GZ_SIM_SYSTEM_PLUGIN_PATH="$PX4_DIR/build/$_PX4_BUILD_DIR_NAME/src/modules/simulation/gz_plugins"
unset _PX4_BUILD_DIR_NAME

echo "[env] SCARECROW_DIR=$SCARECROW_DIR"
echo "[env] GZ_IP=$GZ_IP"
if [ "${SCARECROW_NOLOCKSTEP:-0}" = "1" ]; then
    echo "[env] SCARECROW_NOLOCKSTEP=1 (sim will run at ~100% RTF)"
fi
if [ -n "${SCARECROW_TAKEOFF_TIMEOUT:-}" ]; then
    echo "[env] SCARECROW_TAKEOFF_TIMEOUT=${SCARECROW_TAKEOFF_TIMEOUT}s"
fi
