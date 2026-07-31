#!/bin/bash
# Start Scarecrow Drone Web App (backend + frontend)
# Run from WSL: ./webapp/start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  Scarecrow Drone — Web App"
echo "============================================"

# Align default world with simulation scripts (override before sourcing if needed).
export SCARECROW_DEFAULT_WORLD="${SCARECROW_DEFAULT_WORLD:-hangar_lite}"

# Resolve the Python environment.
#
# Two supported environments, and this script must not assume either:
#   pixi (macOS)      -- `pixi run webapp` sets CONDA_PREFIX; there is no .venv
#                        and there never will be, so the old unconditional
#                        `source .venv/bin/activate` hard-failed here.
#   venv (WSL/Windows)-- the original path, still used by Start Scarecrow.bat.
echo "[webapp] Checking backend dependencies..."
cd "$REPO_ROOT"
if [ -n "${CONDA_PREFIX:-}" ]; then
    echo "[webapp] Using pixi environment: $CONDA_PREFIX"
elif [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "[webapp] Using virtualenv: $REPO_ROOT/.venv"
else
    echo "ERROR: no Python environment found."
    echo "  macOS:       pixi run webapp"
    echo "  WSL/Windows: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

if ! python3 -c "import fastapi, uvicorn" >/dev/null 2>&1; then
    if command -v uv >/dev/null 2>&1; then
        echo "[webapp] Installing backend deps with uv..."
        uv pip install fastapi uvicorn
    else
        echo "[webapp] Backend deps missing; install with: pip install fastapi uvicorn"
    fi
fi

# Start backend
BACKEND_PORT="${BACKEND_PORT:-8000}"
echo "[webapp] Starting backend on port ${BACKEND_PORT}..."
cd "$SCRIPT_DIR/backend"
python3 -m uvicorn app:app --host 0.0.0.0 --port "$BACKEND_PORT" &
BACKEND_PID=$!
sleep 2

if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "ERROR: Backend failed to start"
    exit 1
fi
echo "[webapp] Backend running (PID $BACKEND_PID)"

# Check if npm is available for frontend
if command -v npm &>/dev/null; then
    echo "[webapp] Starting frontend on port 3000..."
    cd "$SCRIPT_DIR/frontend"
    npm install --silent 2>/dev/null
    npm start &
    FRONTEND_PID=$!
    echo "[webapp] Frontend running (PID $FRONTEND_PID)"
    echo ""
    echo "  Backend:  http://localhost:${BACKEND_PORT}"
    echo "  Frontend: http://localhost:3000"
else
    echo ""
    echo "  Backend:  http://localhost:${BACKEND_PORT}"
    echo "  NOTE: npm not found in WSL. Start frontend from Windows:"
    echo "    cd webapp/frontend && npm start"
fi

echo ""
echo "  Press Ctrl+C to stop"
echo "============================================"

# Wait and cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '[webapp] Stopped'" EXIT
wait
