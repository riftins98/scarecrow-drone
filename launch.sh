#!/bin/bash
# Scarecrow Drone — Full Simulation Launcher
# Launches Gazebo + PX4 SITL with the Holybro X500 full sensor stack
# Run this script from inside the Ubuntu VM

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PX4_DIR="$SCRIPT_DIR/px4"

# Check VirtioFS mount (if running via shared folder)
if [ ! -f "$PX4_DIR/build/px4_sitl_default/bin/px4" ]; then
    echo "ERROR: PX4 not built. Run: cd $PX4_DIR && make px4_sitl gz_holybro_x500"
    exit 1
fi

# Inject custom files into PX4
cp "$SCRIPT_DIR/airframes/4022_gz_holybro_x500" \
   "$PX4_DIR/ROMFS/px4fmu_common/init.d-posix/airframes/"
cp "$SCRIPT_DIR/airframes/4022_gz_holybro_x500" \
   "$PX4_DIR/build/px4_sitl_default/etc/init.d-posix/airframes/"
cp "$SCRIPT_DIR/config/server.config" \
   "$PX4_DIR/src/modules/simulation/gz_bridge/"

export GZ_SIM_RESOURCE_PATH="$SCRIPT_DIR/models:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds"
export GZ_SIM_SERVER_CONFIG_PATH="$PX4_DIR/src/modules/simulation/gz_bridge/server.config"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$PX4_DIR/build/px4_sitl_default/src/modules/simulation/gz_plugins"

echo "=== Starting Gazebo Server ==="
gnome-terminal -- bash -c "cd $PX4_DIR && \
  GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH \
  GZ_SIM_SERVER_CONFIG_PATH=$GZ_SIM_SERVER_CONFIG_PATH \
  GZ_SIM_SYSTEM_PLUGIN_PATH=$GZ_SIM_SYSTEM_PLUGIN_PATH \
  gz sim -v 4 -s Tools/simulation/gz/worlds/default.sdf; exec bash" &

echo "Waiting for Gazebo world to be ready..."
sleep 8

echo "=== Starting Gazebo GUI ==="
gnome-terminal -- bash -c "gz sim -v 4 -g; exec bash" &

echo "Waiting for GUI to open..."
sleep 8

echo "=== Starting PX4 SITL ==="
gnome-terminal -- bash -c "cd $PX4_DIR && \
  GZ_SIM_RESOURCE_PATH=$GZ_SIM_RESOURCE_PATH \
  PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=default make px4_sitl gz_holybro_x500; exec bash" &

echo "Waiting for PX4 to start..."
sleep 20

echo "=== Enabling MAVLink broadcast ==="
"$PX4_DIR/build/px4_sitl_default/bin/px4-param" --instance 0 set MAV_0_BROADCAST 1 2>/dev/null || true

echo "=== Arming drone (via MAVLink) ==="
python3 "$SCRIPT_DIR/scripts/arm.py" &
