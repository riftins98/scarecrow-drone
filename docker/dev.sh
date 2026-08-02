#!/usr/bin/env bash
# The pixi workflow, for the container.
#
# macOS drives this project from a shell: `pixi run sim` in one terminal,
# `pixi run fly` in another. Windows and Linux had only the webapp, because
# `docker compose up` starts the UI and there was no way in to anything else.
# The container has always carried the same scripts -- this exposes them.
#
#   bash docker/dev.sh sim              headless sim + camera stream (blocks)
#   bash docker/dev.sh fly [args...]    run the mission against it
#   bash docker/dev.sh sensors          sensor diagnostics, no flight
#   bash docker/dev.sh shell            a shell inside the running container
#   bash docker/dev.sh down             stop and remove it
#
# Flags pass straight through, so the mission takes exactly what it takes on
# macOS:
#
#   bash docker/dev.sh fly --wall-distance 2.5 --target-alt 4.0 --r
#
# The GPU overlay chosen by detect-gpu.sh still applies: this reads the same
# .env, so `dev.sh sim` reaches the GPU exactly as `docker compose up` does.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

SERVICE="sim"
PY="/opt/scarecrow/.venv/bin/python"

# Compose reads COMPOSE_FILE from .env by itself, but `dev.sh sim` needs the
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
        echo "[dev] The simulator is not running." >&2
        echo "[dev] Start it in another terminal first:" >&2
        echo "[dev]     bash docker/dev.sh sim" >&2
        exit 1
    fi
}

CMD="${1:-}"
[ $# -gt 0 ] && shift

case "$CMD" in
    sim)
        export COMPOSE_FILE="$(base_compose_file):docker/compose.dev.yml"
        echo "[dev] Headless sim + camera stream on http://localhost:8080/"
        echo "[dev] Fly it from another terminal:  bash docker/dev.sh fly"
        echo "[dev] compose files: $COMPOSE_FILE"
        exec docker compose up "$SERVICE"
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
        export COMPOSE_FILE="$(base_compose_file):docker/compose.dev.yml"
        exec docker compose down --remove-orphans
        ;;

    ""|-h|--help)
        sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;

    *)
        echo "[dev] unknown command: $CMD" >&2
        echo "[dev] want one of: sim, fly, sensors, map, shell, down" >&2
        exit 2
        ;;
esac
