#!/bin/bash
# Launch the scarecrow drone simulation.
# One command — PX4 manages Gazebo with GUI.
# Usage: ./scripts/shell/launch.sh [world_name] [--headless] [--no-build]
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

# Baseline for _dump_latest_gz_log: any Gazebo log older than this belongs to a
# previous session and must not be presented as diagnostics for this run.
_LAUNCH_START_EPOCH=$(date +%s)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/env.sh"
_LOG_COMPONENT="launch.sim"
source "$SCRIPT_DIR/_log.sh"
_log_init "sim"
_log_host
_log_env_snapshot

WORLD="${1:-${SCARECROW_DEFAULT_WORLD:-hangar_small}}"
HEADLESS_FLAG=""
NO_BUILD=0
if [[ "$2" == "--headless" ]] || [[ "$1" == "--headless" ]]; then
    HEADLESS_FLAG="HEADLESS=1"
    if [[ "$1" == "--headless" ]]; then
        # No world was given (the first arg is the flag), so fall back to the
        # same default as above. This used to hardcode indoor_room, whose SDF
        # no longer exists.
        WORLD="${SCARECROW_DEFAULT_WORLD:-hangar_small}"
    fi
fi

for arg in "$@"; do
    if [[ "$arg" == "--no-build" ]]; then
        NO_BUILD=1
        break
    fi
done

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
echo "  Build PX4: $([ "$NO_BUILD" -eq 1 ] && echo 'NO' || echo 'YES')"
echo "============================================"
echo ""

# --- PX4 target selection ---
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

# --- Cleanup previous session ---
_log_timer_begin cleanup
echo "[launch] Cleaning up..."
pkill -x px4 2>/dev/null || true
pkill -f "gz sim" 2>/dev/null || true
sleep 2
rm -f "$HOME/.px4/px4_lock-0" "$HOME/.px4/px4-sock-0"
_log_timer_end cleanup
echo "[launch] Clean"

# --- Prepare runtime-only Scarecrow assets ---
_log_timer_begin copy_assets
cd "$PX4_DIR"
echo "[launch] Preparing Scarecrow runtime assets..."

# Build/runtime overlays (single source of truth = local repo).
SCARECROW_PX4_GZ_MODELS_DIR="$PX4_DIR/build/scarecrow_gz_models"
SCARECROW_PX4_GZ_WORLDS_DIR="$PX4_DIR/build/scarecrow_gz_worlds"

rm -rf "$SCARECROW_PX4_GZ_MODELS_DIR" 2>/dev/null || true
mkdir -p "$SCARECROW_PX4_GZ_MODELS_DIR"
link_model_dir() {
    local src="$1"
    local dest="$2"
    if [ -e "$dest" ] || [ -L "$dest" ]; then
        rm -rf "$dest" 2>/dev/null || true
    fi
    ln -s "$src" "$dest" 2>/dev/null || true
}
for model_dir in "$SCARECROW_DIR/models"/*; do
    [ -d "$model_dir" ] || continue
    model_name="$(basename "$model_dir")"
    link_model_dir "$model_dir" "$SCARECROW_PX4_GZ_MODELS_DIR/$model_name"
done
if [ -n "${SCARECROW_MODEL_OVERLAY_DIR:-}" ] && [ -d "$SCARECROW_MODEL_OVERLAY_DIR" ]; then
    for model_dir in "$SCARECROW_MODEL_OVERLAY_DIR"/*; do
        [ -d "$model_dir" ] || continue
        model_name="$(basename "$model_dir")"
        link_model_dir "$model_dir" "$SCARECROW_PX4_GZ_MODELS_DIR/$model_name"
    done
fi

# Build a deterministic worlds set for runtime loading.
rm -rf "$SCARECROW_PX4_GZ_WORLDS_DIR" 2>/dev/null || true
mkdir -p "$SCARECROW_PX4_GZ_WORLDS_DIR"
for world_file in "$SCARECROW_DIR/worlds"/*.sdf; do
    [ -f "$world_file" ] || continue
    world_name="$(basename "$world_file")"
    ln -s "$world_file" "$SCARECROW_PX4_GZ_WORLDS_DIR/$world_name" 2>/dev/null || true
done
if [ -n "${SCARECROW_MODEL_OVERLAY_DIR:-}" ] && [ -d "$SCARECROW_MODEL_OVERLAY_DIR" ]; then
    export GZ_SIM_RESOURCE_PATH="$SCARECROW_PX4_GZ_WORLDS_DIR:$SCARECROW_MODEL_OVERLAY_DIR:$SCARECROW_PX4_GZ_MODELS_DIR:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds"
else
    export GZ_SIM_RESOURCE_PATH="$SCARECROW_PX4_GZ_WORLDS_DIR:$SCARECROW_PX4_GZ_MODELS_DIR:$PX4_DIR/Tools/simulation/gz/models:$PX4_DIR/Tools/simulation/gz/worlds"
fi
export PX4_GZ_MODELS="$SCARECROW_PX4_GZ_MODELS_DIR"
export PX4_GZ_WORLDS="$SCARECROW_PX4_GZ_WORLDS_DIR"
export GZ_SIM_SERVER_CONFIG_PATH="$SCARECROW_DIR/config/server.config"
_log_timer_end copy_assets

# --- Build PX4 first ---
_log_timer_begin build_px4
_BUILD_CACHE_HIT=true
[ -f "$PX4_DIR/build/$PX4_BUILD_DIR_NAME/bin/px4" ] || _BUILD_CACHE_HIT=false
if [ "$NO_BUILD" -eq 1 ]; then
    echo "[launch] Skipping PX4 build (--no-build)"
    _log_timer_end build_px4 cache_hit="$_BUILD_CACHE_HIT" target="$PX4_BUILD_TARGET" build_dir="$PX4_BUILD_DIR_NAME" skipped=true
else
    echo "[launch] Building PX4 (this may take a few minutes on first run)..."
    PX4_MAKE_CMAKE_ARGS="${CMAKE_ARGS:-}"
    if [[ "$(uname)" == "Darwin" ]]; then
        # Homebrew protobuf 35 marks RepeatedField::Resize as deprecated.
        # This PX4 submodule still uses that API in gz_bridge, and PX4 builds
        # with -Werror, so suppress only the deprecation warning without
        # changing PX4 source.
        PROTOC_MAJOR="$(protoc --version 2>/dev/null | awk '{print $2}' | cut -d. -f1)"
        if [[ "$PROTOC_MAJOR" =~ ^[0-9]+$ ]] && [ "$PROTOC_MAJOR" -ge 35 ]; then
            CACHE_FILE="$PX4_DIR/build/$PX4_BUILD_DIR_NAME/CMakeCache.txt"
            if [ ! -f "$CACHE_FILE" ] || ! grep -q 'CMAKE_CXX_FLAGS_RELWITHDEBINFO:STRING=.*-Wno-deprecated-declarations' "$CACHE_FILE"; then
                echo "[launch] Protobuf $PROTOC_MAJOR detected; building PX4 with -Wno-deprecated-declarations"
            fi
            PX4_MAKE_CMAKE_ARGS="$PX4_MAKE_CMAKE_ARGS -DCMAKE_CXX_FLAGS_RELWITHDEBINFO:STRING=-O2\\ -g\\ -DNDEBUG\\ -Wno-deprecated-declarations"
        fi
        CMAKE_ARGS="$PX4_MAKE_CMAKE_ARGS" make -j1 "$PX4_BUILD_TARGET"
    else
        make "$PX4_BUILD_TARGET"
    fi
    _log_timer_end build_px4 cache_hit="$_BUILD_CACHE_HIT" target="$PX4_BUILD_TARGET" build_dir="$PX4_BUILD_DIR_NAME" skipped=false
fi

_sync_px4_runtime_assets() {
    local build_dir="$PX4_DIR/build/$PX4_BUILD_DIR_NAME"
    local rootfs_dir="$build_dir/rootfs"
    local rootfs_airframes="$rootfs_dir/etc/init.d-posix/airframes"
    local legacy_airframes="$build_dir/etc/init.d-posix/airframes"
    local runtime_airframe="$rootfs_airframes/4022_gz_holybro_x500"
    local runtime_post="$rootfs_airframes/4022_gz_holybro_x500.post"

    if [ ! -d "$build_dir/etc" ]; then
        echo "[launch] ERROR: PX4 build runtime etc directory is missing: $build_dir/etc" >&2
        return 1
    fi

    # Keep PX4 source/ROMFS untouched. Rebuild rootfs/etc from the PX4 build
    # output, then overlay Scarecrow-owned files from this repo only.
    rm -rf "$rootfs_dir/etc"
    cp -R "$build_dir/etc" "$rootfs_dir/etc"

    mkdir -p "$rootfs_airframes" "$legacy_airframes"
    cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" "$runtime_airframe"
    cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500.post" "$runtime_post"
    cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500" "$legacy_airframes/" 2>/dev/null || true
    cp "$SCARECROW_DIR/airframes/4022_gz_holybro_x500.post" "$legacy_airframes/" 2>/dev/null || true

    for required_param in \
        "EKF2_OF_CTRL" \
        "EKF2_OF_QMIN" \
        "EKF2_OF_POS_X" \
        "EKF2_RNG_CTRL" \
        "EKF2_RNG_POS_Z" \
        "EKF2_RNG_A_HMAX"; do
        if ! grep -q "$required_param" "$runtime_airframe"; then
            echo "[launch] ERROR: runtime airframe is missing $required_param: $runtime_airframe" >&2
            return 1
        fi
    done
    echo "[launch] Runtime airframe synced from repo and verified: $runtime_airframe"

    # PX4 persists params in rootfs/parameters.bson. The airframe uses
    # `param set-default`, so stale persisted values can override the repo
    # airframe and break GPS-denied optical-flow hold. Reset only the generated
    # build rootfs by default; set SCARECROW_RESET_PX4_PARAMS=0 to preserve it.
    if [ "${SCARECROW_RESET_PX4_PARAMS:-1}" = "1" ]; then
        rm -f "$rootfs_dir/parameters.bson" "$rootfs_dir/parameters_backup.bson"
        echo "[launch] Reset PX4 persisted params in build rootfs so airframe defaults apply"
    else
        echo "[launch] Preserving PX4 persisted params (SCARECROW_RESET_PX4_PARAMS=0)"
    fi

    if [ -f "$rootfs_dir/gz_env.sh" ]; then
        sed -i.bak \
            -e "s|^export PX4_GZ_MODELS=.*|export PX4_GZ_MODELS=$SCARECROW_PX4_GZ_MODELS_DIR|" \
            -e "s|^export PX4_GZ_WORLDS=.*|export PX4_GZ_WORLDS=$SCARECROW_PX4_GZ_WORLDS_DIR|" \
            -e "s|^export PX4_GZ_SERVER_CONFIG=.*|export PX4_GZ_SERVER_CONFIG=$SCARECROW_DIR/config/server.config|" \
            "$rootfs_dir/gz_env.sh"
        rm -f "$rootfs_dir/gz_env.sh.bak"
        cp "$rootfs_dir/gz_env.sh" "$build_dir/gz_env.sh"
    fi
}

_log_timer_begin runtime_assets
echo "[launch] Syncing Scarecrow runtime assets into PX4 build rootfs..."
_sync_px4_runtime_assets
_log_timer_end runtime_assets

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

fi

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

    # Only a log created during THIS run describes this failure. Anything older is
    # from a previous session and is actively misleading — it may show a healthy run
    # and bury the real error. Observed 2026-07-31: a failed launch printed a
    # successful log from 2026-06-25.
    if [[ -n "${_LAUNCH_START_EPOCH:-}" ]]; then
        local log_epoch
        log_epoch=$(date -r "$log_file" +%s 2>/dev/null || echo 0)
        if (( log_epoch < _LAUNCH_START_EPOCH )); then
            echo "[launch] No Gazebo log produced by this run — gz sim never started."
            echo "[launch] (Newest log on disk is from a previous session: $latest_dir)"
            echo "[launch] Reproduce the failure directly with:"
            echo "[launch]   gz sim --headless-rendering -s -r -v1 \"\$SCARECROW_DIR/worlds/$WORLD.sdf\""
            return
        fi
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

PX4_BIN="$PX4_DIR/build/$PX4_BUILD_DIR_NAME/bin/px4"
PX4_WORKDIR="$PX4_DIR/build/$PX4_BUILD_DIR_NAME"
PX4_RUNTIME_DIR="$PX4_WORKDIR/rootfs"
PX4_STARTUP_FILE="$PX4_WORKDIR/etc/init.d-posix/rcS"

_log_event run_px4_begin headless_flag="$HEADLESS_FLAG" pose_flag="$POSE_FLAG" world="$WORLD" run_target="$PX4_RUN_TARGET" gz_target="direct_holybro_x500"

if [ "${SCARECROW_PXH_INTERACTIVE:-0}" = "1" ]; then
    (cd "$PX4_RUNTIME_DIR" && eval $HEADLESS_FLAG $POSE_FLAG \
        PX4_SYS_AUTOSTART=4022 \
        PX4_SIM_MODEL=gz_holybro_x500 \
        PX4_GZ_WORLD="$WORLD" \
        PX4_GZ_MODELS="$SCARECROW_PX4_GZ_MODELS_DIR" \
        PX4_GZ_WORLDS="$SCARECROW_PX4_GZ_WORLDS_DIR" \
        GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH" \
        GZ_SIM_SERVER_CONFIG_PATH="$SCARECROW_DIR/config/server.config" \
        "$PX4_BIN" -s "$PX4_STARTUP_FILE" "$PX4_WORKDIR" -w "$PX4_RUNTIME_DIR")
else
    (cd "$PX4_RUNTIME_DIR" && eval $HEADLESS_FLAG $POSE_FLAG \
        PX4_SYS_AUTOSTART=4022 \
        PX4_SIM_MODEL=gz_holybro_x500 \
        PX4_GZ_WORLD="$WORLD" \
        PX4_GZ_MODELS="$SCARECROW_PX4_GZ_MODELS_DIR" \
        PX4_GZ_WORLDS="$SCARECROW_PX4_GZ_WORLDS_DIR" \
        GZ_SIM_RESOURCE_PATH="$GZ_SIM_RESOURCE_PATH" \
        GZ_SIM_SERVER_CONFIG_PATH="$SCARECROW_DIR/config/server.config" \
        "$PX4_BIN" -s "$PX4_STARTUP_FILE" "$PX4_WORKDIR" -w "$PX4_RUNTIME_DIR") \
        < "$PXH_FIFO" \
        > >(tee "$PXH_INJECT_LOG")
fi

_log_event run_px4_end exit_code=$?
# Cleanup is handled by the EXIT trap (cleanup_pxh).
