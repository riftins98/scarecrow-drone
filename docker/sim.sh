#!/usr/bin/env bash
# The pixi workflow, for the container.
#
# macOS drives this project from a shell: `pixi run sim` in one terminal,
# `pixi run fly` in another. Windows and Linux had only the webapp, because
# `docker compose up` starts the UI and there was no way in to anything else.
# The container has always carried the same scripts -- this exposes them.
#
#   bash docker/sim.sh sim [flags]      launch the sim (blocks)
#   bash docker/sim.sh fly [args...]    run the mission against it
#   bash docker/sim.sh sensors          sensor diagnostics, no flight
#   bash docker/sim.sh shell            a shell inside the running container
#   bash docker/sim.sh down             stop and remove it
#
# `sim` takes launch_with_stream.sh's own flags, unchanged. --headless gives
# a headless sim; omit it and Gazebo opens a window, exactly as the shell
# script defines it:
#
#   bash docker/sim.sh sim --headless --fixed      headless, fixed camera
#   bash docker/sim.sh sim --fixed                 GUI window
#   bash docker/sim.sh sim --headless --drone_view hangar_lite
#
# Mission flags pass through the same way, so a command is identical to its
# macOS counterpart:
#
#   bash docker/sim.sh fly --wall-distance 2.5 --target-alt 4.0 --r
#
# The GPU overlay chosen by detect-gpu.sh still applies: this reads the same
# .env, so the sim reaches the GPU exactly as `docker compose up` does.
#
# A GUI launch additionally needs a display reachable from the container
# (WSLg on Windows 11, or an X server). Without one Gazebo will fail to open
# a window -- the flags are honoured either way, the display is a separate
# prerequisite.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

SERVICE="sim"
PY="/opt/scarecrow/.venv/bin/python"

# Compose reads COMPOSE_FILE from .env by itself, but `sim.sh sim` needs the
# dev overlay appended to whatever detect-gpu.sh chose. Read it, extend it,
# and pass it back through the environment rather than editing the file --
# .env describes the machine, not this invocation.
base_compose_file() {
    if [ -f .env ] && grep -q '^COMPOSE_FILE=' .env; then
        grep '^COMPOSE_FILE=' .env | tail -1 | cut -d= -f2-
    else
        echo "docker-compose.yml"
    fi
}

require_running() {
    if [ -z "$(docker compose ps -q "$SERVICE" 2>/dev/null)" ]; then
        echo "[sim] The simulator is not running." >&2
        echo "[sim] Start it in another terminal first:" >&2
        echo "[sim]     bash docker/sim.sh sim" >&2
        exit 1
    fi
}

CMD="${1:-}"
[ $# -gt 0 ] && shift

case "$CMD" in
    sim)
        # Call the launcher directly rather than going through the entrypoint's
        # sim mode, which hardcodes --headless. The image already supports
        # command passthrough, so this needs no rebuild -- and it means the
        # flags below are literally launch_with_stream.sh's flags, not a
        # reimplementation of them that could drift.
        export COMPOSE_FILE="$(base_compose_file):docker/compose.sim.yml"
        set -- "${@:---headless --fixed}"
        case " $* " in
            *" --fixed "*|*" --center "*|*" --drone_cam "*|*" --drone_view "*) ;;
            *)
                echo "[sim] No camera flag given; adding --fixed." >&2
                set -- "$@" --fixed
                ;;
        esac
        case " $* " in
            *" --headless "*) ;;
            *) echo "[sim] No --headless: Gazebo will try to open a window." >&2
               echo "[sim] That needs a display the container can reach (WSLg)." >&2 ;;
        esac
        echo "[sim] Stream on http://localhost:8080/"
        echo "[sim] Fly it from another terminal:  bash docker/sim.sh fly"
        exec docker compose run --rm --service-ports "$SERVICE" \
            ./scripts/shell/launch_with_stream.sh \
            --no-open --no-build --port "${STREAM_PORT:-8080}" "$@"
        ;;

    fly)
        require_running
        # -T because the mission is not interactive and a TTY would mangle the
        # log lines the webapp's parser and the acceptance checklist rely on.
        exec docker compose exec -T "$SERVICE" \
            "$PY" scripts/flight/hangar_circuit_pursuit.py "$@"
        ;;

    sensors)
        require_running
        exec docker compose exec -T "$SERVICE" \
            "$PY" scripts/flight/sensor_check.py "$@"
        ;;

    map)
        require_running
        exec docker compose exec -T "$SERVICE" \
            "$PY" scripts/flight/room_circuit_map.py "$@"
        ;;

    shell)
        require_running
        exec docker compose exec "$SERVICE" bash
        ;;

    down)
        export COMPOSE_FILE="$(base_compose_file):docker/compose.sim.yml"
        exec docker compose down --remove-orphans
        ;;

    ""|-h|--help)
        sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;

    *)
        echo "[sim] unknown command: $CMD" >&2
        echo "[sim] want one of: sim, fly, sensors, map, shell, down" >&2
        exit 2
        ;;
esac
