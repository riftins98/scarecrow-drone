#!/bin/bash
# Start Scarecrow Drone Web App on macOS.
# Opens backend and frontend in separate Terminal windows.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_ACTIVATE="$REPO_ROOT/.venv/bin/activate"

escape_for_osascript() {
    printf "%s" "$1" | sed "s/'/'\\\\''/g"
}

if [ ! -f "$VENV_ACTIVATE" ]; then
    echo "ERROR: Python venv not found at $VENV_ACTIVATE"
    echo "Create it first:"
    echo "  cd '$REPO_ROOT'"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r webapp/backend/requirements.txt"
    exit 1
fi

if [ ! -f "$FRONTEND_DIR/package.json" ]; then
    echo "ERROR: Frontend package.json not found at $FRONTEND_DIR"
    exit 1
fi

BACKEND_CMD="cd '$(escape_for_osascript "$BACKEND_DIR")' && source '$(escape_for_osascript "$VENV_ACTIVATE")' && echo '[backend] starting FastAPI on http://localhost:8000' && python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload; echo; echo '[backend] exited'; exec \${SHELL:-/bin/zsh}"
FRONTEND_CMD="cd '$(escape_for_osascript "$FRONTEND_DIR")' && if [ ! -d node_modules ]; then echo '[frontend] installing npm dependencies...'; npm install; fi && echo '[frontend] starting React on http://localhost:3000' && npm start; echo; echo '[frontend] exited'; exec \${SHELL:-/bin/zsh}"

echo "Starting Scarecrow web app..."
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"

osascript -e "tell application \"Terminal\" to do script \"$BACKEND_CMD\""
osascript -e "tell application \"Terminal\" to do script \"$FRONTEND_CMD\""

echo "Opened backend and frontend Terminal windows."
