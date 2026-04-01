@echo off
title Law Digital Human System Startup
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "BACKEND_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

echo ===================================================
echo        Law Digital Human System - Quick Start
echo ===================================================

echo [1/3] Starting Docker services...
cd /d "%ROOT%"
docker-compose up -d

echo [2/3] Starting Backend API...
if not exist "%BACKEND_PY%" (
  echo [ERROR] Backend Python not found: %BACKEND_PY%
  echo Please recreate backend virtual env first.
  pause
  exit /b 1
)
start "Backend API Service" "%BACKEND_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir "%BACKEND_DIR%"

echo Waiting for backend health check...
set "READY=0"
for /L %%I in (1,1,20) do (
  powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 2) | Out-Null; exit 0 } catch { exit 1 }"
  if not errorlevel 1 (
    set "READY=1"
    goto :BACKEND_READY
  )
  timeout /t 1 >nul
)

:BACKEND_READY
if "%READY%"=="1" (
  echo Backend is up.
) else (
  echo [WARN] Backend not ready yet. Frontend will still start; wait a few seconds then refresh browser.
)

echo [3/3] Starting Frontend Service...
start "Frontend Web Service" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo.
echo ===================================================
echo Startup sequence initiated!
echo.
echo Backend API URL: http://127.0.0.1:8000
echo Backend API Docs: http://127.0.0.1:8000/docs
echo.
echo Please check the "Frontend Web Service" terminal 
echo for the local URL (Usually http://localhost:5173/)
echo.
echo Note: Do not close the newly opened terminal 
echo windows if you want the services to keep running.
echo ===================================================
pause
