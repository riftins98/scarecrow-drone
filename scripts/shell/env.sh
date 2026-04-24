#!/bin/bash
# Shared environment for all scarecrow-drone scripts.
# Source this file: source scripts/env.sh

# Resolve repo root (works from any subdirectory)
export SCARECROW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PX4_DIR="$SCARECROW_DIR/px4"

# Gazebo resource paths (includes our custom models and worlds)
export GZ_SIM_RESOURCE_PATH="$SCARECROW_DIR/models:$SCARECROW_DIR/worlds:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds"
export GZ_SIM_SERVER_CONFIG_PATH="$PX4_DIR/src/modules/simulation/gz_bridge/server.config"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins"

# Network — Gazebo needs real IP (not 127.0.0.1, loopback breaks multicast)
if command -v ipconfig &>/dev/null; then
    export GZ_IP="$(ipconfig getifaddr en0 2>/dev/null)"
elif command -v hostname &>/dev/null; then
    export GZ_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi
export GZ_PARTITION=px4

# WSL GPU routing — force NVIDIA discrete GPU (was defaulting to Intel iGPU, tanked RTF)
export MESA_D3D12_DEFAULT_ADAPTER_NAME=NVIDIA

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

echo "[env] SCARECROW_DIR=$SCARECROW_DIR"
echo "[env] GZ_IP=$GZ_IP"
