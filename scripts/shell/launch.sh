#!/bin/bash
# Launch the scarecrow drone simulation.
# One command — PX4 manages Gazebo with GUI.
# Usage: ./scripts/shell/launch.sh [world_name] [--headless]
#   Default world: indoor_room
#   Set spawn position: PX4_GZ_MODEL_POSE="-7,-7,0,0,0,0" ./scripts/shell/launch.sh
#
# CHANGELOG
#   2026-05-02 — Added auto-injection of `commander set_ekf_origin 0 0 0` and
#                `commander set_heading 0` into PX4 stdin via FIFO once startup
#                completes. Mirrors what webapp/backend/services/sim_service.py
#                does (see _send_pxh_command). Without this, headless launches
#                (e.g. launch_with_stream.sh) cannot arm in GPS-denied mode
#                because home position never converges.
#                Original is preserved at scripts/shell/launch.sh.bak — to
#                revert: `mv scripts/shell/launch.sh.bak scripts/shell/launch.sh`.
set -e
trap 'echo "[launch] ERROR: script failed at line $LINENO — exit code $?"' ERR

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/env.sh"
_LOG_COMPONENT="launch.sim"
source "$SCRIPT_DIR/_log.sh"
_log_init "sim"
_log_host
_log_env_snapshot

WORLD="${1:-indoor_room}"
HEADLESS_FLAG=""
if [[ "$2" == "--headless" ]] || [[ "$1" == "--headless" ]]; then
    HEADLESS_FLAG="HEADLESS=1"
    if [[ "$1" == "--headless" ]]; then
        WORLD="indoor_room"
    fi
fi

# Accept both "world_name" and "world_name.sdf" inputs.
WORLD="${WORLD%.sdf}"

_log_event launch_start \
    world="$WORLD" \
    headless="$([ -n "$HEADLESS_FLAG" ] && echo true || echo false)" \
    spawn_pose="\"${PX4_GZ_MODEL_POSE:-0,0,0,0,0,0}\""

echo "============================================"
echo "  Scarecrow Drone — Simulation Launcher"
echo "  World: $WORLD"
echo "  Spawn: ${PX4_GZ_MODEL_POSE:-0,0,0,0,0,0}"
echo "  GUI: $([ -z "$HEADLESS_FLAG" ] && echo 'YES' || echo 'NO')"
echo "============================================"
echo ""

# --- Cleanup previous session ---
_log_timer_begin cleanup
echo "[launch] Cleaning up..."
pkill -x px4 2>/dev/null || true
pkill -f "gz sim" 2>/dev/null || true
sleep 2
rm -f "$HOME/.px4/px4_lock-0" "$HOME/.px4/px4-sock-0"
_log_timer_end cleanup
echo "[launch] Clean"

# --- Copy airframe to ROMFS (always exists, build copies it to rootfs) ---
_log_timer_begin copy_assets
cd "$PX4_DIR"
echo "[launch] Copying airframe and config..."
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" ROMFS/px4fmu_common/init.d-posix/airframes/
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500.post" ROMFS/px4fmu_common/init.d-posix/airframes/
cp "$SCARECROW_DIR/config/server.config" src/modules/simulation/gz_bridge/

# Build against clean mirrors (single source of truth = local repo).
SCARECROW_PX4_GZ_MODELS_DIR="$PX4_DIR/build/scarecrow_gz_models"
SCARECROW_PX4_GZ_WORLDS_DIR="$PX4_DIR/build/scarecrow_gz_worlds"

rm -rf "$SCARECROW_PX4_GZ_MODELS_DIR" 2>/dev/null || true
mkdir -p "$SCARECROW_PX4_GZ_MODELS_DIR"
for model_dir in "$SCARECROW_DIR/models"/*; do
    [ -d "$model_dir" ] || continue
    model_name="$(basename "$model_dir")"
    ln -s "$model_dir" "$SCARECROW_PX4_GZ_MODELS_DIR/$model_name" 2>/dev/null || true
done

# Build a deterministic worlds set for PX4 CMake target generation.
# This avoids accidental duplicate/invalid files from polluting targets.
rm -rf "$SCARECROW_PX4_GZ_WORLDS_DIR" 2>/dev/null || true
mkdir -p "$SCARECROW_PX4_GZ_WORLDS_DIR"
for world_file in "$SCARECROW_DIR/worlds"/*.sdf; do
    [ -f "$world_file" ] || continue
    world_name="$(basename "$world_file")"
    ln -s "$world_file" "$SCARECROW_PX4_GZ_WORLDS_DIR/$world_name" 2>/dev/null || true
done
export GZ_SIM_RESOURCE_PATH="$SCARECROW_PX4_GZ_WORLDS_DIR:$SCARECROW_PX4_GZ_MODELS_DIR"
export PX4_GZ_WORLDS_DIR="$SCARECROW_PX4_GZ_WORLDS_DIR"
_log_timer_end copy_assets

# --- Build PX4 first (creates rootfs with airframe) ---
# SCARECROW_NOLOCKSTEP=1 (set automatically on WSL by env.sh) switches to the
# nolockstep build target so the sim runs at ~100% real-time-factor.
# That target builds into build/px4_sitl_nolockstep instead of build/px4_sitl_default.
PX4_BUILD_TARGET="px4_sitl"
PX4_BUILD_DIR_NAME="px4_sitl_default"
PX4_RUN_TARGET="px4_sitl"
if [ "${SCARECROW_NOLOCKSTEP:-0}" = "1" ]; then
    PX4_BUILD_TARGET="px4_sitl_nolockstep"
    PX4_BUILD_DIR_NAME="px4_sitl_nolockstep"
    PX4_RUN_TARGET="px4_sitl_nolockstep"
    _log_event nolockstep_enabled
    echo "[launch] SCARECROW_NOLOCKSTEP=1 — using nolockstep targets (~100% RTF)"
fi

_log_timer_begin build_px4
_BUILD_CACHE_HIT=true
[ -f "$PX4_DIR/build/$PX4_BUILD_DIR_NAME/bin/px4" ] || _BUILD_CACHE_HIT=false
echo "[launch] Building PX4 (this may take a few minutes on first run)..."
if [[ "$(uname)" == "Darwin" ]]; then
    make -j1 "$PX4_BUILD_TARGET"
else
    make "$PX4_BUILD_TARGET"
fi
_log_timer_end build_px4 cache_hit="$_BUILD_CACHE_HIT" target="$PX4_BUILD_TARGET" build_dir="$PX4_BUILD_DIR_NAME"

if [[ "$(uname)" == "Darwin" ]]; then
    # PX4's Gazebo optical-flow plugin links against libOpticalFlow.dylib via
    # @rpath, but the dependency is installed under the build-local OpticalFlow dir.
    # Put a stable symlink in the rpath searched by libOpticalFlowSystem.dylib.
    OPTICAL_FLOW_LIB="$PX4_DIR/build/$PX4_BUILD_DIR_NAME/OpticalFlow/install/lib/libOpticalFlow.dylib"
    OPTICAL_FLOW_RPATH_LIB="$PX4_DIR/build/$PX4_BUILD_DIR_NAME/external/Install/lib/libOpticalFlow.dylib"
    if [ -f "$OPTICAL_FLOW_LIB" ]; then
        mkdir -p "$(dirname "$OPTICAL_FLOW_RPATH_LIB")"
        ln -sf "$OPTICAL_FLOW_LIB" "$OPTICAL_FLOW_RPATH_LIB"
    fi

    # Some copied/restored PX4 model files can end up user-only readable, which
    # makes Gazebo report model://LW20 as missing even when the files exist.
    if [ -d "$PX4_DIR/Tools/simulation/gz/models/LW20" ]; then
        chmod -R a+rX,u+w "$PX4_DIR/Tools/simulation/gz/models/LW20" 2>/dev/null || true
    fi
fi

# --- Copy airframe to rootfs (in case build didn't pick it up from ROMFS) ---
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" "build/$PX4_BUILD_DIR_NAME/rootfs/etc/init.d-posix/airframes/" 2>/dev/null || true
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" "build/$PX4_BUILD_DIR_NAME/etc/init.d-posix/airframes/" 2>/dev/null || true
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500.post" "build/$PX4_BUILD_DIR_NAME/rootfs/etc/init.d-posix/airframes/" 2>/dev/null || true
cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500.post" "build/$PX4_BUILD_DIR_NAME/etc/init.d-posix/airframes/" 2>/dev/null || true

# --- Launch PX4 + Gazebo ---
echo "[launch] Starting PX4 + Gazebo..."
echo ""
POSE_FLAG=""
if [ -n "${PX4_GZ_MODEL_POSE}" ]; then
    POSE_FLAG="PX4_GZ_MODEL_POSE=${PX4_GZ_MODEL_POSE}"
fi

if [ "${SCARECROW_PXH_INTERACTIVE:-0}" != "1" ]; then
    # --- pxh command auto-injection (added 2026-05-02) ---
    # Mirrors webapp/backend/services/sim_service.py: after PX4 prints
    # "Startup script returned successfully", inject the two commander commands
    # that set EKF origin + heading. Required for arming in GPS-denied mode.
    # A FIFO supplies stdin to PX4 so we can write to it from a background watcher.
    PXH_FIFO="$(mktemp -u /tmp/scarecrow_pxh.XXXXXX).fifo"
    mkfifo "$PXH_FIFO"
    # Hold the FIFO open so PX4 doesn't see EOF on its stdin (would exit pxh).
    # Sleep is killed by trap on script exit.
    exec 9<>"$PXH_FIFO"
    cleanup_pxh() {
        [ -n "${PXH_INJECT_PID:-}" ] && kill "$PXH_INJECT_PID" 2>/dev/null || true
        exec 9>&- 2>/dev/null || true
        rm -f "$PXH_FIFO" 2>/dev/null || true
        [ -n "${PXH_INJECT_LOG:-}" ] && rm -f "$PXH_INJECT_LOG" 2>/dev/null || true
    }
    trap cleanup_pxh EXIT

    # Tee make's stdout so we can both display it AND watch for the readiness line.
    if [[ "$(uname)" == "Darwin" ]]; then
        # On macOS/BSD mktemp, trailing suffixes after XXXXXX are not portable.
        # Also clean up a legacy stub path that can block mktemp on repeated runs.
        [ -f /tmp/scarecrow_launch.XXXXXX.log ] && rm -f /tmp/scarecrow_launch.XXXXXX.log
        PXH_INJECT_LOG="$(mktemp /tmp/scarecrow_launch.XXXXXX)"
    else
        PXH_INJECT_LOG="$(mktemp /tmp/scarecrow_launch.XXXXXX.log)"
    fi
    _log_event fifo_setup fifo="$PXH_FIFO" tee_log="$PXH_INJECT_LOG"
    (
        # Watcher: tail -F follows the log even before tee creates content;
        # exits when "Startup script returned successfully" appears, after
        # injecting the same two commander commands sim_service.py sends.
        # Same delays as sim_service.py (2s before first, 1s between).
        _watcher_log() {
            local ts; ts="$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%S.000Z")"
            local line="[$ts INFO launch.fifo] event=$1"; shift
            for kv in "$@"; do line+=" $kv"; done
            echo "$line" >&2
            [ -n "$_LOG_FILE" ] && echo "$line" >> "$_LOG_FILE"
        }
        _watcher_log watcher_started
        tail -n +1 -F "$PXH_INJECT_LOG" 2>/dev/null | while IFS= read -r line; do
            if [[ "$line" == *"Startup script returned successfully"* ]]; then
                _watcher_log px4_startup_seen
                sleep 4
                echo "commander set_ekf_origin 0 0 0" >&9
                _watcher_log injected cmd="\"commander set_ekf_origin 0 0 0\""
                sleep 1
                echo "commander set_heading 0" >&9
                _watcher_log injected cmd="\"commander set_heading 0\""
                _watcher_log watcher_done
                break
            fi
        done
    ) &
    PXH_INJECT_PID=$!
else
    _log_event fifo_skipped reason="interactive_pxh"
fi

_dump_latest_gz_log() {
    local latest_dir
    latest_dir=$(ls -t "$HOME/.gz/sim/log" 2>/dev/null | head -n 1)
    if [[ -z "$latest_dir" ]]; then
        echo "[launch] No Gazebo log directory found under ~/.gz/sim/log"
        return
    fi

    local log_file="$HOME/.gz/sim/log/$latest_dir/server_console.log"
    if [[ ! -f "$log_file" ]]; then
        echo "[launch] Gazebo log not found: $log_file"
        return
    fi

    echo "[launch] Gazebo log (tail 200): $log_file"
    tail -n 200 "$log_file"
}

# --- Gazebo early-exit guard ---
# If gz sim exits during startup, dump the latest server log to help diagnose.
(
    sleep 15
    if ! pgrep -f "gz sim" >/dev/null 2>&1; then
        echo "[launch] WARNING: gz sim not running after startup window"
        _dump_latest_gz_log
    fi
) &
GZ_GUARD_PID=$!

_log_event run_px4_begin headless_flag="$HEADLESS_FLAG" pose_flag="$POSE_FLAG" world="$WORLD" run_target="$PX4_RUN_TARGET"

if [ "${SCARECROW_PXH_INTERACTIVE:-0}" = "1" ]; then
    eval $HEADLESS_FLAG $POSE_FLAG PX4_GZ_WORLD="$WORLD" make "$PX4_RUN_TARGET" gz_holybro_x500
else
    eval $HEADLESS_FLAG $POSE_FLAG PX4_GZ_WORLD="$WORLD" make "$PX4_RUN_TARGET" gz_holybro_x500 \
        < "$PXH_FIFO" \
        > >(tee "$PXH_INJECT_LOG")
fi

_log_event run_px4_end exit_code=$?
# Cleanup is handled by the EXIT trap (cleanup_pxh).
