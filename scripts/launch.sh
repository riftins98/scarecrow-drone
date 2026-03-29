#!/bin/bash
# Launch the full scarecrow drone simulation.
# Opens two Terminal.app windows: Gazebo + PX4
# Usage: ./scripts/launch.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCARECROW_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  Scarecrow Drone — Simulation Launcher"
echo "============================================"
echo ""

# --- Cleanup any previous session ---
echo "[launch] Cleaning up previous session..."
pkill -f "gz sim" 2>/dev/null || true
pkill -x px4 2>/dev/null || true
sleep 2

# Remove stale files (may need sudo if owned by another user)
if [ -f /tmp/px4_lock-0 ] || [ -f /tmp/px4-sock-0 ]; then
    echo "[launch] Removing stale PX4 files (may need password)..."
    sudo rm -f /tmp/px4_lock-0 /tmp/px4-sock-0
fi

echo "[launch] Clean"
echo ""

# --- Open Terminal 1: Gazebo ---
echo "[launch] Opening Gazebo terminal..."
osascript -e "
tell application \"Terminal\"
    activate
    set gazeboTab to do script \"cd '$SCARECROW_DIR' && bash scripts/start_gz.sh\"
    set custom title of front window to \"Gazebo Server\"
end tell
"

# --- Wait for Gazebo to initialize ---
echo "[launch] Waiting for Gazebo to load (this takes ~15 seconds)..."
sleep 5

source "$SCRIPT_DIR/env.sh" > /dev/null 2>&1
ATTEMPTS=60
while [ $ATTEMPTS -gt 0 ]; do
    if GZ_IP="$GZ_IP" GZ_PARTITION="$GZ_PARTITION" gz service -i --service "/world/default/scene/info" 2>&1 | grep -q "Service providers"; then
        echo "[launch] Gazebo is ready!"
        break
    fi
    ATTEMPTS=$((ATTEMPTS - 1))
    if [ $ATTEMPTS -eq 0 ]; then
        echo "[launch] WARNING: Could not confirm Gazebo readiness, continuing anyway..."
        break
    fi
    sleep 1
done

echo ""

# --- Open Terminal 2: PX4 ---
echo "[launch] Opening PX4 terminal..."
osascript -e "
tell application \"Terminal\"
    activate
    set px4Tab to do script \"cd '$SCARECROW_DIR' && bash scripts/start_px4.sh\"
    set custom title of front window to \"PX4 SITL\"
end tell
"

echo ""
echo "============================================"
echo "  Terminals opened!"
echo ""
echo "  Wait for PX4 terminal to show:"
echo "    'PX4 READY — Run hover_test.py now'"
echo ""
echo "  Then in a new terminal:"
echo "    cd $SCARECROW_DIR"
echo "    source .venv-mavsdk/bin/activate"
echo "    python3 scripts/hover_test.py"
echo "============================================"
