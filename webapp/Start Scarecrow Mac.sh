#!/bin/bash
# Start Scarecrow Drone Web App — macOS launcher
# Opens backend and frontend each in a new Terminal window, then opens browser.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  Scarecrow Drone — Web App (macOS)"
echo "============================================"

# Activate venv
source "$REPO_ROOT/.venv-mavsdk/bin/activate" 2>/dev/null || {
    echo "ERROR: .venv-mavsdk not found."
    echo "Run: python3 -m venv .venv-mavsdk && source .venv-mavsdk/bin/activate && pip install -r requirements.txt"
    exit 1
}

# Ensure fastapi/uvicorn available
pip install fastapi uvicorn -q 2>/dev/null

echo "[webapp] Starting backend in new Terminal window..."
osascript -e "tell application \"Terminal\" to do script \"source '$REPO_ROOT/.venv-mavsdk/bin/activate' && cd '$SCRIPT_DIR/backend' && python3 -m uvicorn app:app --host 0.0.0.0 --port 8000\""

echo "[webapp] Starting frontend in new Terminal window..."
osascript -e "tell application \"Terminal\" to do script \"cd '$SCRIPT_DIR/frontend' && npm install --silent && npm start\""

echo ""
echo "============================================"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo ""
echo "  Two Terminal windows opened."
echo "  Close them to stop the services."
echo "============================================"

# Wait for frontend to boot then open browser
sleep 6
open http://localhost:3000
