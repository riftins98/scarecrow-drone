#!/bin/bash
# Shared structured logger for scarecrow shell scripts.
# Source this AFTER env.sh: `source "$SCRIPT_DIR/_log.sh"`.
#
# Provides:
#   _log_init <prefix>             — set up output/logs/<prefix>_<ts>.log
#   _log_event <event> [k=v ...]  — emit one structured line, levels via env
#   _log_info / _log_warn / _log_error — same but with explicit level
#   _log_timer_begin <name>        — record start time
#   _log_timer_end <name> [k=v]    — emit *_end with elapsed_ms
#   _log_host                      — dump host info (uname, free mem, gz ver, etc.)
#
# Format mirrors scarecrow.logging_setup so all logs share one grep surface:
#   [<iso8601-utc> LEVEL component] event=<name> key=value ...

if [ -z "${SCARECROW_DIR:-}" ]; then
    echo "[_log.sh] ERROR: SCARECROW_DIR not set; source env.sh first" >&2
    return 1 2>/dev/null || exit 1
fi

_LOG_DIR="$SCARECROW_DIR/output/logs"
mkdir -p "$_LOG_DIR"

_LOG_FILE=""
_LOG_COMPONENT="${_LOG_COMPONENT:-shell}"
declare -A _LOG_TIMERS 2>/dev/null || true  # bash 4+; older bash silently no-ops

_log_iso_now() {
    # ISO-8601 UTC with millis. `date` doesn't have millis on macOS; fall back to seconds there.
    if date -u +%3N 2>/dev/null | grep -q '^[0-9]'; then
        date -u +"%Y-%m-%dT%H:%M:%S.%3NZ"
    else
        date -u +"%Y-%m-%dT%H:%M:%S.000Z"
    fi
}

_log_init() {
    local prefix="${1:-launch}"
    local ts
    ts="$(date -u +"%Y%m%dT%H%M%SZ")"
    _LOG_FILE="$_LOG_DIR/${prefix}_${ts}.log"
    : > "$_LOG_FILE"
    _log_event run_start prefix="$prefix" log_file="$_LOG_FILE" pid=$$
}

# _log_emit <level> <event> [extra k=v args...]
_log_emit() {
    local level="$1"; shift
    local event="$1"; shift
    local ts; ts="$(_log_iso_now)"
    local line="[$ts $level $_LOG_COMPONENT] event=$event"
    local arg
    for arg in "$@"; do
        line+=" $arg"
    done
    echo "$line"
    if [ -n "$_LOG_FILE" ]; then
        echo "$line" >> "$_LOG_FILE"
    fi
}

_log_event() { _log_emit INFO "$@"; }
_log_info()  { _log_emit INFO "$@"; }
_log_warn()  { _log_emit WARN "$@"; }
_log_error() { _log_emit ERROR "$@"; }

# Timer using monotonic seconds (date +%s.%N gives high-res on Linux).
_log_now_ns() { date +%s%N 2>/dev/null || date +%s000000000; }

_log_timer_begin() {
    local name="$1"
    _LOG_TIMERS["$name"]="$(_log_now_ns)"
    _log_event "${name}_begin"
}

_log_timer_end() {
    local name="$1"; shift
    local start="${_LOG_TIMERS[$name]:-}"
    local elapsed_ms="?"
    if [ -n "$start" ]; then
        local now; now="$(_log_now_ns)"
        elapsed_ms=$(( (now - start) / 1000000 ))
    fi
    _log_event "${name}_end" elapsed_ms="$elapsed_ms" "$@"
}

_log_host() {
    local kern; kern="$(uname -srm 2>/dev/null | tr -d '\n')"
    local cpus; cpus="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo ?)"
    local mem_mb; mem_mb="$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo ?)"
    local gz_ver; gz_ver="$(gz sim --version 2>/dev/null | head -1 | tr -d '\n' | tr ' ' '_' || echo unknown)"
    local py_ver; py_ver="$(python3 --version 2>/dev/null | tr -d '\n' | tr ' ' '_' || echo unknown)"
    local is_wsl="false"
    if [ -r /proc/version ] && grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
        is_wsl="true"
    fi
    _log_event host_info \
        kernel="\"$kern\"" \
        cpus="$cpus" \
        mem_mb="$mem_mb" \
        gz_ver="$gz_ver" \
        py_ver="$py_ver" \
        is_wsl="$is_wsl" \
        scarecrow_dir="\"$SCARECROW_DIR\""
}

_log_env_snapshot() {
    # Log the env vars we care about (without dumping full env).
    _log_event env_snapshot \
        gz_ip="${GZ_IP:-}" \
        gz_partition="${GZ_PARTITION:-}" \
        px4_dir="\"${PX4_DIR:-}\"" \
        scarecrow_takeoff_timeout="${SCARECROW_TAKEOFF_TIMEOUT:-}" \
        px4_gz_no_follow="${PX4_GZ_NO_FOLLOW:-}" \
        px4_gz_model_pose="\"${PX4_GZ_MODEL_POSE:-}\"" \
        headless="${HEADLESS:-}"
}
