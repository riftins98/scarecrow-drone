#!/bin/bash
# Shared environment for all scarecrow-drone scripts.
# Source this file: source scripts/env.sh

# Resolve repo root (works from any subdirectory)
export SCARECROW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PX4_DIR="$SCARECROW_DIR/px4"

# Gazebo resource paths
export GZ_SIM_RESOURCE_PATH="$SCARECROW_DIR/models:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds"
export GZ_SIM_SERVER_CONFIG_PATH="$PX4_DIR/src/modules/simulation/gz_bridge/server.config"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins"

# Network — Gazebo needs real IP (not 127.0.0.1, loopback breaks multicast)
export GZ_IP="$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')"
export GZ_PARTITION=px4

# macOS SDK workaround (broken symlink in macOS 26)
if [[ "$(uname)" == "Darwin" ]]; then
    export SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.2.sdk
    export CXXFLAGS="-cxx-isystem ${SDKROOT}/usr/include/c++/v1 -isysroot ${SDKROOT}"
    export CMAKE_PREFIX_PATH="/opt/homebrew/opt/qt@5:$CMAKE_PREFIX_PATH"
fi

echo "[env] SCARECROW_DIR=$SCARECROW_DIR"
echo "[env] GZ_IP=$GZ_IP"
