@echo off
setlocal enabledelayedexpansion

REM Get the directory where this batch file is located
set "ROOT=%~dp0"
if "!ROOT:~-1!"=="\" set "ROOT=!ROOT:~0,-1!"

echo Starting SlipSense Backend...
start "SlipSense Backend" cmd /k "cd /d "!ROOT!\backend" & python -m pip install -r requirements.txt >nul 2>&1 & python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000"

echo Starting SlipSense Frontend...
timeout /t 3 /nobreak >nul
start "SlipSense Frontend" cmd /k "cd /d "!ROOT!\frontend" & npm install >nul 2>&1 & npm run dev"

echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo.
pause

echo.
echo SlipSense is starting...
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo.
echo Two new windows should open shortly (backend & frontend).
pause
