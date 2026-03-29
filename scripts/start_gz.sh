#!/bin/bash
# Start Gazebo server with the scarecrow drone world.
# Uses the custom textured world for optical flow.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/env.sh"

echo "============================================"
echo "  Gazebo Server — Scarecrow Drone World"
echo "============================================"

# Copy latest server config (includes OpticalFlowSystem plugin)
cp "$SCARECROW_DIR/config/server.config" "$PX4_DIR/src/modules/simulation/gz_bridge/"

cd "$PX4_DIR"

echo "[gz] Starting Gazebo with custom world..."
echo "[gz] World: $SCARECROW_DIR/worlds/default.sdf"
echo "[gz] Plugin path: $GZ_SIM_SYSTEM_PLUGIN_PATH"
echo ""

# -r = run immediately (no GUI needed)
# -s = server only (headless)
exec gz sim -v 4 -r -s "$SCARECROW_DIR/worlds/default.sdf"
