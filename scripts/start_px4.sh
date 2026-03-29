#!/bin/bash
# Start PX4 SITL and apply all runtime configuration.
# Waits for Gazebo to be ready, then launches PX4, then configures EKF2.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/env.sh"

echo "============================================"
echo "  PX4 SITL — Holybro X500 (GPS-Denied)"
echo "============================================"

cd "$PX4_DIR"

# --- Copy airframe to all required locations ---
echo "[px4] Copying airframe 4022_gz_holybro_x500..."
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" ROMFS/px4fmu_common/init.d-posix/airframes/ 2>/dev/null || true
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" build/px4_sitl_default/etc/init.d-posix/airframes/ 2>/dev/null || true
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" build/px4_sitl_default/rootfs/etc/init.d-posix/airframes/ 2>/dev/null || true

# --- Wait for Gazebo to be ready ---
echo "[px4] Waiting for Gazebo world..."
ATTEMPTS=60
while [ $ATTEMPTS -gt 0 ]; do
    if GZ_IP="$GZ_IP" GZ_PARTITION="$GZ_PARTITION" gz service -i --service "/world/default/scene/info" 2>&1 | grep -q "Service providers"; then
        echo "[px4] Gazebo is ready"
        break
    fi
    ATTEMPTS=$((ATTEMPTS - 1))
    if [ $ATTEMPTS -eq 0 ]; then
        echo "[px4] ERROR: Gazebo not ready after 60 seconds. Is start_gz.sh running?"
        exit 1
    fi
    sleep 1
done

# --- Build and launch PX4 in background ---
echo "[px4] Building and launching PX4 SITL..."
PX4_GZ_STANDALONE=1 PX4_GZ_WORLD=default make px4_sitl gz_holybro_x500 &
PX4_PID=$!

# --- Wait for PX4 to be running ---
echo "[px4] Waiting for PX4 to start..."
for i in $(seq 1 90); do
    if pgrep -x px4 > /dev/null 2>&1; then
        echo "[px4] PX4 process detected, waiting for init..."
        sleep 10
        break
    fi
    sleep 1
done

if ! pgrep -x px4 > /dev/null 2>&1; then
    echo "[px4] ERROR: PX4 failed to start"
    exit 1
fi

# --- Apply runtime parameters ---
BIN="$PX4_DIR/build/px4_sitl_default/bin"
echo ""
echo "[px4] Applying runtime configuration..."

$BIN/px4-param set EKF2_BARO_CTRL 0 2>/dev/null
echo "  EKF2_BARO_CTRL = 0 (barometer disabled)"

$BIN/px4-param set EKF2_OF_QMIN 0 2>/dev/null
echo "  EKF2_OF_QMIN = 0 (accept all flow quality)"

echo "[px4] Restarting EKF2 with new params..."
$BIN/px4-ekf2 stop 2>/dev/null
sleep 1
$BIN/px4-ekf2 start 2>/dev/null
sleep 3

echo "[px4] Setting EKF origin..."
$BIN/px4-commander set_ekf_origin 0 0 0 2>/dev/null
$BIN/px4-commander set_heading 0 2>/dev/null

# --- Verify ---
echo ""
echo "[px4] Verifying EKF2..."
$BIN/px4-ekf2 status 2>&1

echo ""
echo "============================================"
echo "  PX4 READY — Run hover_test.py now"
echo "============================================"
echo ""
echo "  source .venv-mavsdk/bin/activate"
echo "  python3 scripts/hover_test.py"
echo ""

# Keep running (PX4 is in background)
wait $PX4_PID
