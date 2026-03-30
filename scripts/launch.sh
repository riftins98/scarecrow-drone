#!/bin/bash
# Launch the scarecrow drone simulation.
# One command — PX4 manages Gazebo with GUI.
# Usage: ./scripts/launch.sh [world_name] [--headless]
#   Default world: indoor_room
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/env.sh"

WORLD="${1:-indoor_room}"
HEADLESS_FLAG=""
if [[ "$2" == "--headless" ]] || [[ "$1" == "--headless" ]]; then
    HEADLESS_FLAG="HEADLESS=1"
    if [[ "$1" == "--headless" ]]; then
        WORLD="indoor_room"
    fi
fi

echo "============================================"
echo "  Scarecrow Drone — Simulation Launcher"
echo "  World: $WORLD"
echo "  GUI: $([ -z "$HEADLESS_FLAG" ] && echo 'YES' || echo 'NO')"
echo "============================================"
echo ""

# --- Cleanup previous session ---
echo "[launch] Cleaning up..."
pkill -x px4 2>/dev/null || true
pkill -f "gz sim" 2>/dev/null || true
sleep 2
rm -f /tmp/px4_lock-0 /tmp/px4-sock-0 2>/dev/null
echo "[launch] Clean"

# --- Copy airframe to ROMFS (always exists, build copies it to rootfs) ---
cd "$PX4_DIR"
echo "[launch] Copying airframe and config..."
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" ROMFS/px4fmu_common/init.d-posix/airframes/
cp "$SCARECROW_DIR/config/server.config" src/modules/simulation/gz_bridge/

# Copy custom models and world to PX4 dirs
cp -r "$SCARECROW_DIR/models/holybro_x500" "$PX4_DIR/Tools/simulation/gz/models/" 2>/dev/null || true
cp -r "$SCARECROW_DIR/models/mono_cam" "$PX4_DIR/Tools/simulation/gz/models/" 2>/dev/null || true
cp "$SCARECROW_DIR/worlds/"*.sdf "$PX4_DIR/Tools/simulation/gz/worlds/" 2>/dev/null || true

# --- Build PX4 first (creates rootfs with airframe) ---
echo "[launch] Building PX4 (this may take a few minutes on first run)..."
make px4_sitl 2>&1 | tail -3

# --- Copy airframe to rootfs (in case build didn't pick it up from ROMFS) ---
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" build/px4_sitl_default/rootfs/etc/init.d-posix/airframes/ 2>/dev/null || true
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" build/px4_sitl_default/etc/init.d-posix/airframes/ 2>/dev/null || true

# --- Launch PX4 + Gazebo ---
echo "[launch] Starting PX4 + Gazebo..."
echo ""
eval $HEADLESS_FLAG PX4_GZ_WORLD="$WORLD" make px4_sitl gz_holybro_x500
