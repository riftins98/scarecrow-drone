#!/bin/bash
# Launch the scarecrow drone simulation + start camera stream.
# Usage:
#   ./scripts/shell/launch_with_stream.sh [world_name] [--headless] [--port 8080] [--no-open]
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

echo "============================================"
echo "  Scarecrow Drone — Sim + Live Stream"
echo "  World: $WORLD"
echo "  Stream: http://localhost:${STREAM_PORT}/"
echo "  Open Browser: $([ "$OPEN_BROWSER" -eq 1 ] && echo 'YES' || echo 'NO')"
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

_log_event step world="$WORLD" port="$STREAM_PORT" stream_mode="$STREAM_MODE" headless="$([ -n "$HEADLESS_FLAG" ] && echo true || echo false)"

echo "[launch_with_stream] Step 1/4: create the sim"
_log_timer_begin step1_create_sim
# Start the simulator (background, log to file to avoid pxh> prompt)
"$SCRIPT_DIR/launch.sh" "$WORLD" "$HEADLESS_FLAG" \
    > "$REPO_ROOT/output/launch_sim.log" 2>&1 &
SIM_PID=$!
_log_event sim_spawned pid="$SIM_PID" sim_log="$REPO_ROOT/output/launch_sim.log"
echo "[launch_with_stream] Simulator PID:  $SIM_PID"
echo "[launch_with_stream] Sim log:        $REPO_ROOT/output/launch_sim.log"
_log_timer_end step1_create_sim

echo "[launch_with_stream] Step 2/4: create the drone"
_log_timer_begin step2_drone_topic
# Wait for PX4 sitl instance/drone topics to appear (up to 90s)
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
# Wait specifically for the fixed external camera topic (up to 90s)
# Accept possible Gazebo auto-suffixes on model names (e.g., fixed_cam_0).
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
# Start the stream server (background)
OPEN_FLAG=""
if [ "$OPEN_BROWSER" -eq 1 ]; then
    OPEN_FLAG="--open"
fi
if [ "$STREAM_MODE" = "webrtc" ]; then
    if ! "$PYTHON_BIN" -c "import aiortc, aiohttp, av" >/dev/null 2>&1; then
        echo "[launch_with_stream] WARNING: WebRTC dependencies missing in $PYTHON_BIN"
        echo "[launch_with_stream] Falling back to MJPEG stream mode"
        STREAM_MODE="mjpeg"
    fi
fi

if [ "$STREAM_MODE" = "webrtc" ]; then
    PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" "$REPO_ROOT/scripts/stream_camera_webrtc.py" \
        --port "$STREAM_PORT" --fps "$STREAM_FPS" --threads "$STREAM_THREADS" \
        $OPEN_FLAG ${CAMERA_TOPIC:+--topic "$CAMERA_TOPIC"} \
        > "$REPO_ROOT/output/stream_camera.log" 2>&1 &
else
    PYTHONPATH="$REPO_ROOT" "$PYTHON_BIN" "$REPO_ROOT/scripts/stream_camera.py" \
        --port "$STREAM_PORT" --fps "$STREAM_FPS" --quality "$STREAM_QUALITY" --threads "$STREAM_THREADS" \
        $OPEN_FLAG ${CAMERA_TOPIC:+--topic "$CAMERA_TOPIC"} \
        > "$REPO_ROOT/output/stream_camera.log" 2>&1 &
fi
STREAM_PID=$!
_log_event stream_spawned pid="$STREAM_PID" mode="$STREAM_MODE" port="$STREAM_PORT"
echo "[launch_with_stream] Stream PID:     $STREAM_PID"
echo "[launch_with_stream] Stream log:     $REPO_ROOT/output/stream_camera.log"
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
_log_timer_end step4_stream
_log_event ready stream_url="http://localhost:${STREAM_PORT}/" sim_pid="$SIM_PID" stream_pid="$STREAM_PID"

# Wait for simulator to exit
wait $SIM_PID
_log_event sim_exited

# Cleanup stream when sim exits
if ps -p $STREAM_PID > /dev/null 2>&1; then
    kill $STREAM_PID
    _log_event stream_killed
fi
_log_event run_end
