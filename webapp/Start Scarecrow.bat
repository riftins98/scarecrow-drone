@echo off
title Scarecrow Drone - Web App
echo ============================================
echo   Scarecrow Drone — Web App
echo ============================================
echo.

:: Sync only webapp backend and detection script to WSL (avoid touching PX4 files)
echo [webapp] Syncing files to WSL...
wsl -d Ubuntu-22.04 -- bash -c "mkdir -p /home/tomer/scarecrow-drone/webapp/backend/database /home/tomer/scarecrow-drone/webapp/backend/services /home/tomer/scarecrow-drone/webapp/output /home/tomer/scarecrow-drone/models/yolo && cp '/mnt/c/projects/finale project/sim/scarecrow-drone/webapp/backend/app.py' /home/tomer/scarecrow-drone/webapp/backend/ && cp '/mnt/c/projects/finale project/sim/scarecrow-drone/webapp/backend/database/db.py' /home/tomer/scarecrow-drone/webapp/backend/database/ && cp '/mnt/c/projects/finale project/sim/scarecrow-drone/webapp/backend/services/sim_service.py' /home/tomer/scarecrow-drone/webapp/backend/services/ && cp '/mnt/c/projects/finale project/sim/scarecrow-drone/webapp/backend/services/detection_service.py' /home/tomer/scarecrow-drone/webapp/backend/services/ && cp '/mnt/c/projects/finale project/sim/scarecrow-drone/scripts/flight/detect_pigeons.py' /home/tomer/scarecrow-drone/scripts/flight/ && [ -f /home/tomer/scarecrow-drone/models/yolo/best_v4.pt ] || cp '/mnt/c/projects/finale project/sim/scarecrow-drone/models/yolo/best_v4.pt' /home/tomer/scarecrow-drone/models/yolo/"

:: Start backend in WSL
echo [webapp] Starting backend...
start "Scarecrow Backend" wsl -d Ubuntu-22.04 -- bash -c "cd /home/tomer/scarecrow-drone/webapp/backend && source /home/tomer/scarecrow-drone/.venv-mavsdk/bin/activate && python3 -m uvicorn app:app --host 0.0.0.0 --port 5000"

:: Wait for backend
timeout /t 3 /nobreak >nul

:: Install frontend deps if needed and start
echo [webapp] Starting frontend...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo [webapp] Installing frontend dependencies...
    call npm install
)
start "Scarecrow Frontend" cmd /c "npm start"

:: npm start opens browser automatically, no need to open again

echo.
echo ============================================
echo   Backend:  http://localhost:5000
echo   Frontend: http://localhost:3000
echo   Close this window to stop all services.
echo ============================================
pause
