#!/bin/bash
# Launch the scarecrow drone simulation + start camera stream.
# Usage:
#   ./scripts/shell/launch_with_stream.sh [world_name] [--headless] [--port 8080] [--no-open] [--background]
# Default world: drone_garage_pigeon_3d
set -e
trap 'echo "[launch_with_stream] ERROR at line $LINENO — exit code $?"' ERR
cleanup() {
    if [ -n "${STREAM_PID:-}" ] && ps -p "$STREAM_PID" > /dev/null 2>&1; then
        kill "$STREAM_PID" 2>/dev/null || true
    fi
    if [ -n "${SIM_PID:-}" ] && ps -p "$SIM_PID" > /dev/null 2>&1; then
        kill "$SIM_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/env.sh"
_LOG_COMPONENT="launch.stream"
source "$SCRIPT_DIR/_log.sh"
_log_init "stream"
_log_host
_log_env_snapshot
REPO_ROOT="$SCARECROW_DIR"

WORLD="${1:-drone_garage_pigeon_3d}"
HEADLESS_FLAG=""
STREAM_PORT="8080"
DEFAULT_POSE="5,-4.5,0,0,0,0"
OPEN_BROWSER=1
INTERACTIVE_PXH=1
STREAM_FPS="${STREAM_FPS:-24}"
STREAM_QUALITY="${STREAM_QUALITY:-68}"
STREAM_THREADS="${STREAM_THREADS:-2}"
STREAM_MODE="${STREAM_MODE:-webrtc}"

# Default spawn pose (can be overridden by exporting PX4_GZ_MODEL_POSE)
if [ -z "${PX4_GZ_MODEL_POSE}" ]; then
    export PX4_GZ_MODEL_POSE="$DEFAULT_POSE"
fi

if [[ "$2" == "--headless" ]] || [[ "$1" == "--headless" ]]; then
    HEADLESS_FLAG="--headless"
    if [[ "$1" == "--headless" ]]; then
        WORLD="drone_garage_pigeon_3d"
    fi
fi

if [[ "$3" == "--port" ]]; then
    STREAM_PORT="$4"
elif [[ "$2" == "--port" ]]; then
    STREAM_PORT="$3"
fi
if [[ "$1" == "--no-open" ]] || [[ "$2" == "--no-open" ]] || [[ "$3" == "--no-open" ]] || [[ "$4" == "--no-open" ]]; then
    OPEN_BROWSER=0
fi
for arg in "$@"; do
    if [[ "$arg" == "--background" ]]; then
        INTERACTIVE_PXH=0
        break
    fi
done

echo "============================================"
echo "  Scarecrow Drone — Sim + Live Stream"
echo "  World: $WORLD"
echo "  Stream: http://localhost:${STREAM_PORT}/"
echo "  Open Browser: $([ "$OPEN_BROWSER" -eq 1 ] && echo 'YES' || echo 'NO')"
echo "  Interactive PXH: $([ "$INTERACTIVE_PXH" -eq 1 ] && echo 'YES' || echo 'NO')"
echo "  Stream Mode: $STREAM_MODE"
echo "  Stream FPS: $STREAM_FPS | JPEG Quality: $STREAM_QUALITY | Camera Threads: $STREAM_THREADS"
echo "============================================"

# Pick python (prefer venv if present)
PYTHON_BIN="python3"
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
fi

# Ensure output directory exists for logs
mkdir -p "$REPO_ROOT/output"

_log_event step world="$WORLD" port="$STREAM_PORT" stream_mode="$STREAM_MODE" headless="$([ -n "$HEADLESS_FLAG" ] && echo true || echo false)" interactive_pxh="$([ "$INTERACTIVE_PXH" -eq 1 ] && echo true || echo false)"

# Stream worker: waits for the drone+camera topics to come up, then execs the
# stream server in its own subshell. Backgrounded so the main script can
# (optionally) keep launch.sh in the foreground for an interactive pxh prompt.
start_stream_worker() {
    echo "[launch_with_stream] Step 2/4: create the drone"
    _log_timer_begin step2_drone_topic
    DRONE_READY=0
    for _ in {1..90}; do
        if gz topic -l 2>/dev/null | grep -q -E "/model/holybro_x500"; then
            DRONE_READY=1
            break
        fi
        sleep 1
    done
    _log_timer_end step2_drone_topic detected="$DRONE_READY"
    if [ "$DRONE_READY" -eq 0 ]; then
        _log_warn drone_topic_timeout
        echo "[launch_with_stream] WARNING: drone model topic not detected yet"
    fi

    echo "[launch_with_stream] Step 3/4: set the camera"
    _log_timer_begin step3_camera_topic
    CAMERA_TOPIC=""
    for _ in {1..90}; do
        CAMERA_TOPIC=$(gz topic -l 2>/dev/null | grep -m 1 -E "/model/(fixed_cam|fixed_cam_[0-9]+|mono_cam_hd|mono_cam_hd_[0-9]+)/link/camera_link/sensor/camera/image$" || true)
        if [ -n "$CAMERA_TOPIC" ]; then
            break
        fi
        sleep 1
    done
    _log_timer_end step3_camera_topic camera_topic="\"${CAMERA_TOPIC:-}\""

    echo "[launch_with_stream] Step 4/4: run camera stream"
    _log_timer_begin step4_stream
    OPEN_FLAG=""
    if [ "$OPEN_BROWSER" -eq 1 ]; then
        OPEN_FLAG="--open"
    fi
    if [ "$STREAM_MODE" = "webrtc" ]; then
        if ! "$PYTHON_BIN" -c "import aiortc, aiohttp, av" >/dev/null 2>&1; then
            _log_warn webrtc_deps_missing python_bin="$PYTHON_BIN"
            echo "[launch_with_stream] WARNING: WebRTC dependencies missing in $PYTHON_BIN"
            echo "[launch_with_stream] Falling back to MJPEG stream mode"
            STREAM_MODE="mjpeg"
        fi
    fi

    if [ -z "$CAMERA_TOPIC" ]; then
        _log_error camera_topic_missing
        echo "[launch_with_stream] ERROR: fixed camera topic not found; refusing to start stream on the drone camera"
        echo "[launch_with_stream] Check world/model setup for model names: fixed_cam / mono_cam_hd"
        echo "[launch_with_stream] Available camera topics:"
        gz topic -l 2>/dev/null | grep -E "camera_link/sensor/camera/image$|sensor/camera/image$" || true
        exit 1
    else
        echo "[launch_with_stream] Camera topic:   $CAMERA_TOPIC"
    fi

    _log_event stream_exec mode="$STREAM_MODE" port="$STREAM_PORT" topic="\"${CAMERA_TOPIC:-}\""
    _log_timer_end step4_stream
    if [ "$STREAM_MODE" = "webrtc" ]; then
        exec env PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" "$REPO_ROOT/scripts/stream_camera_webrtc.py" \
            --port "$STREAM_PORT" --fps "$STREAM_FPS" --threads "$STREAM_THREADS" \
            $OPEN_FLAG ${CAMERA_TOPIC:+--topic "$CAMERA_TOPIC"}
    else
        exec env PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" "$REPO_ROOT/scripts/stream_camera.py" \
            --port "$STREAM_PORT" --fps "$STREAM_FPS" --quality "$STREAM_QUALITY" --threads "$STREAM_THREADS" \
            $OPEN_FLAG ${CAMERA_TOPIC:+--topic "$CAMERA_TOPIC"}
    fi
}

echo "[launch_with_stream] Step 1/4: create the sim"
_log_timer_begin step1_create_sim
if [ "$INTERACTIVE_PXH" -eq 1 ]; then
    # Interactive pxh mode: stream worker in background, launch.sh in foreground
    # so the user gets a live `pxh>` prompt to drive PX4 by hand.
    start_stream_worker > "$REPO_ROOT/output/stream_camera.log" 2>&1 &
    STREAM_PID=$!
    _log_event stream_worker_spawned pid="$STREAM_PID" stream_log="$REPO_ROOT/output/stream_camera.log" interactive=true
    echo "[launch_with_stream] Stream worker PID: $STREAM_PID"
    echo "[launch_with_stream] Stream log:        $REPO_ROOT/output/stream_camera.log"
    _log_timer_end step1_create_sim
    _log_event ready stream_url="http://localhost:${STREAM_PORT}/" stream_pid="$STREAM_PID" interactive=true
    "$SCRIPT_DIR/launch.sh" "$WORLD" "$HEADLESS_FLAG"
    _log_event sim_exited
else
    # Background mode: sim and stream both detached, sim log goes to file.
    "$SCRIPT_DIR/launch.sh" "$WORLD" "$HEADLESS_FLAG" \
        > "$REPO_ROOT/output/launch_sim.log" 2>&1 &
    SIM_PID=$!
    _log_event sim_spawned pid="$SIM_PID" sim_log="$REPO_ROOT/output/launch_sim.log"
    echo "[launch_with_stream] Simulator PID:  $SIM_PID"
    echo "[launch_with_stream] Sim log:        $REPO_ROOT/output/launch_sim.log"

    start_stream_worker > "$REPO_ROOT/output/stream_camera.log" 2>&1 &
    STREAM_PID=$!
    _log_event stream_worker_spawned pid="$STREAM_PID" stream_log="$REPO_ROOT/output/stream_camera.log" interactive=false
    echo "[launch_with_stream] Stream worker PID: $STREAM_PID"
    echo "[launch_with_stream] Stream log:        $REPO_ROOT/output/stream_camera.log"
    _log_timer_end step1_create_sim
    _log_event ready stream_url="http://localhost:${STREAM_PORT}/" sim_pid="$SIM_PID" stream_pid="$STREAM_PID" interactive=false

    wait $SIM_PID
    _log_event sim_exited
fi

# Cleanup stream when sim exits (covers both paths above).
if [ -n "${STREAM_PID:-}" ] && ps -p "$STREAM_PID" > /dev/null 2>&1; then
    kill "$STREAM_PID" 2>/dev/null || true
    _log_event stream_killed pid="$STREAM_PID"
fi
_log_event run_end
