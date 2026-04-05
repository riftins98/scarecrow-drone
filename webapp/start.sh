#!/bin/bash
# Start Scarecrow Drone Web App (backend + frontend)
# Run from WSL: ./webapp/start.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  Scarecrow Drone — Web App"
echo "============================================"

# Install backend deps if needed
echo "[webapp] Checking backend dependencies..."
cd "$REPO_ROOT"
source .venv-mavsdk/bin/activate 2>/dev/null || {
    echo "ERROR: .venv-mavsdk not found. Run: python3 -m venv .venv-mavsdk && pip install -r requirements.txt"
    exit 1
}
pip install fastapi uvicorn -q 2>/dev/null

# Start backend
echo "[webapp] Starting backend on port 5000..."
cd "$SCRIPT_DIR/backend"
python3 -m uvicorn app:app --host 0.0.0.0 --port 5000 &
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
    echo "  Backend:  http://localhost:5000"
    echo "  Frontend: http://localhost:3000"
else
    echo ""
    echo "  Backend:  http://localhost:5000"
    echo "  NOTE: npm not found in WSL. Start frontend from Windows:"
    echo "    cd webapp/frontend && npm start"
fi

echo ""
echo "  Press Ctrl+C to stop"
echo "============================================"

# Wait and cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '[webapp] Stopped'" EXIT
wait
