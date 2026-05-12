@echo off
setlocal EnableDelayedExpansion
title Scarecrow Drone - Web App

REM Parse args: -d / --dev / /d enables developer mode (show log windows + verbose)
set "DEV_MODE=0"
for %%A in (%*) do (
    if /I "%%~A"=="-d" set "DEV_MODE=1"
    if /I "%%~A"=="--dev" set "DEV_MODE=1"
    if /I "%%~A"=="/d" set "DEV_MODE=1"
    if /I "%%~A"=="-h" goto :usage
    if /I "%%~A"=="--help" goto :usage
    if /I "%%~A"=="/?" goto :usage
)

echo ============================================
echo   Scarecrow Drone - Web App Launcher
if "%DEV_MODE%"=="1" (
    echo   Mode: DEVELOPER  ^(verbose, log windows visible^)
) else (
    echo   Mode: NORMAL     ^(use -d for dev logs^)
)
echo ============================================
echo.

REM --- Paths (WSL view) ---
REM Backend runs from WSL-native ext4 copy (~/scarecrow-drone) for fast build I/O.
REM Frontend stays on Windows (this folder) so npm/Node run native.
set "WSL_REPO=/home/tomeraf/scarecrow-drone"
set "WSL_VENV=%WSL_REPO%/.venv-mavsdk/bin/activate"
set "WSL_BACKEND=%WSL_REPO%/webapp/backend"
set "FRONTEND_DIR=%~dp0frontend"

REM --- Sanity checks ---
echo [check] Verifying WSL is available...
wsl -- bash -c "echo ok" >nul 2>&1
if errorlevel 1 (
    echo ERROR: WSL is not available. Install/enable WSL2 and try again.
    pause
    exit /b 1
)

echo [check] Verifying project venv exists in WSL...
wsl -- bash -c "[ -f '%WSL_VENV%' ] && echo ok" 2>nul | findstr /b "ok" >nul
if errorlevel 1 (
    echo ERROR: Python venv not found at %WSL_VENV%
    echo Create it first:
    echo   wsl
    echo   cd %WSL_REPO%
    echo   python3 -m venv .venv-mavsdk
    echo   source .venv-mavsdk/bin/activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

echo [check] Verifying frontend exists...
if not exist "%FRONTEND_DIR%\package.json" (
    echo ERROR: Frontend not found at %FRONTEND_DIR%
    pause
    exit /b 1
)

REM --- Ensure backend Python deps are installed (first-run convenience) ---
echo [check] Verifying backend Python dependencies...
wsl -- bash -c "source '%WSL_VENV%' && python3 -c 'import uvicorn, fastapi' 2>/dev/null" >nul 2>&1
if errorlevel 1 (
    echo [check] Installing backend dependencies into venv ^(first run^)...
    wsl -- bash -c "source '%WSL_VENV%' && pip install -r '%WSL_REPO%/webapp/backend/requirements.txt'"
    if errorlevel 1 (
        echo.
        echo ERROR: pip install failed. Most common causes:
        echo   1^) WSL networking is broken. Try in PowerShell: wsl --shutdown
        echo   2^) DNS broken in WSL. Try:
        echo        wsl -- sudo bash -c "echo nameserver 8.8.8.8 ^> /etc/resolv.conf"
        echo.
        pause
        exit /b 1
    )
    echo [check] Backend dependencies installed.
)

REM --- Kill anything already listening on the ports ---
echo [cleanup] Killing any stale processes on ports 3000 / 8000...
wsl -- bash -c "pkill -f 'uvicorn app:app' 2>/dev/null; true"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)

REM --- Start backend in WSL ---
echo.
echo [backend] Starting FastAPI on port 8000 ^(WSL^)...
if "%DEV_MODE%"=="1" (
    start "Scarecrow Backend ^(dev^)" wsl -- bash -c "cd '%WSL_BACKEND%' && source '%WSL_VENV%' && python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload"
) else (
    REM Normal mode: log to a WSL-side path so the redirect works inside bash.
    REM The log is reachable from Windows via \\wsl$\Ubuntu\tmp\scarecrow_backend.log.
    start "Scarecrow Backend" /MIN wsl -- bash -c "cd '%WSL_BACKEND%' && source '%WSL_VENV%' && python3 -m uvicorn app:app --host 0.0.0.0 --port 8000 > /tmp/scarecrow_backend.log 2>&1"
    echo   Logs: \\wsl$\Ubuntu\tmp\scarecrow_backend.log  ^(or run: wsl cat /tmp/scarecrow_backend.log^)
)

REM --- Wait for backend to be reachable ---
echo [backend] Waiting for it to come up...
set "BACKEND_READY=0"
for /L %%i in (1,1,30) do (
    timeout /t 1 /nobreak >nul
    curl -s -o nul -w "%%{http_code}" http://localhost:8000/api/health 2>nul | findstr /b "200" >nul
    if not errorlevel 1 (
        set "BACKEND_READY=1"
        goto :backend_up
    )
)
:backend_up
if "%BACKEND_READY%"=="0" (
    echo.
    echo ERROR: Backend did not respond on port 8000 within 30s.
    if "%DEV_MODE%"=="1" (
        echo The dev backend window should be open -- check it for the traceback.
    ) else (
        echo --- Last 30 lines of backend log: -----------------------------------
        wsl -- bash -c "tail -n 30 /tmp/scarecrow_backend.log 2>/dev/null || echo (no log file at /tmp/scarecrow_backend.log)"
        echo ---------------------------------------------------------------------
    )
    echo.
    echo Frontend will NOT start because the backend is down. Fix the backend
    echo error above, then re-run this launcher.
    echo.
    REM Clean up the half-running backend process before we exit.
    wsl -- bash -c "pkill -f 'uvicorn app:app' 2>/dev/null; true"
    pause
    exit /b 1
)
echo [backend] Ready at http://localhost:8000

REM --- Frontend dependencies ---
echo.
echo [frontend] Checking npm dependencies...
cd /d "%FRONTEND_DIR%"
if not exist "node_modules" (
    echo [frontend] First run -- installing dependencies ^(this may take a minute^)...
    call npm install
    if errorlevel 1 (
        echo ERROR: npm install failed.
        pause
        exit /b 1
    )
)

REM --- Start frontend ---
echo [frontend] Starting React dev server on port 3000...
if "%DEV_MODE%"=="1" (
    start "Scarecrow Frontend ^(dev^)" cmd /c "npm start"
) else (
    set "FRONTEND_LOG=%TEMP%\scarecrow_frontend.log"
    start "Scarecrow Frontend" /MIN cmd /c "npm start > %TEMP%\scarecrow_frontend.log 2>&1"
    echo   Logs: %TEMP%\scarecrow_frontend.log
)

echo.
echo ============================================
echo   Backend:  http://localhost:8000
echo   API docs: http://localhost:8000/docs
echo   Frontend: http://localhost:3000  ^(opens in browser shortly^)
echo.
echo   Close this window to stop everything.
echo ============================================
echo.

REM --- Wait for user to close, then clean up ---
echo Press any key to stop all services and exit...
pause >nul

echo.
echo [cleanup] Stopping services...
wsl -- bash -c "pkill -f 'uvicorn app:app' 2>/dev/null; true"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":3000" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)
taskkill /F /FI "WINDOWTITLE eq Scarecrow Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq Scarecrow Frontend*" >nul 2>&1
echo [cleanup] Done.
exit /b 0


:usage
echo Usage: Start Scarecrow.bat [-d^|--dev]
echo.
echo   -d, --dev    Developer mode: shows backend and frontend log windows
echo                with full output ^(useful for debugging^).
echo.
echo   Default:     Normal mode. Logs go to %%TEMP%%\scarecrow_*.log.
echo.
exit /b 0
