@echo off
title Law Digital Human System Startup
setlocal EnableDelayedExpansion

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "FRONTEND_DIR=%ROOT%frontend"
set "BACKEND_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NGROK_EXE=%ROOT%tools\ngrok\ngrok.exe"
set "NGROK_CFG=%ROOT%tools\ngrok\ngrok.yml"
set "ENV_FILE=%BACKEND_DIR%\.env"

echo ===================================================
echo        Law Digital Human System - Quick Start
echo ===================================================

echo [1/4] Starting Docker services...
cd /d "%ROOT%"
docker-compose up -d

echo [2/4] Starting ngrok tunnel for backend (AUC requires public URL)...
set "NGROK_URL="
if exist "%NGROK_EXE%" (
  for /f "usebackq delims=" %%U in (`powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri http://127.0.0.1:4040/api/tunnels -TimeoutSec 2; ($r.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1 -ExpandProperty public_url) } catch { '' }"`) do (
    set "NGROK_URL=%%U"
  )
  if not defined NGROK_URL (
    taskkill /IM ngrok.exe /F >nul 2>nul
    timeout /t 1 >nul
    start "Ngrok Tunnel Service" cmd /k ""%NGROK_EXE%" http 8000 --log stdout --log-format json --config "%NGROK_CFG%""
  ) else (
    echo Reusing existing ngrok tunnel...
  )
  echo Waiting for ngrok public URL...
  set "NGROK_READY=0"
  for /L %%I in (1,1,90) do (
    for /f "usebackq delims=" %%U in (`powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri http://127.0.0.1:4040/api/tunnels -TimeoutSec 2; ($r.tunnels | Where-Object { $_.proto -eq 'https' } | Select-Object -First 1 -ExpandProperty public_url) } catch { '' }"`) do (
      set "NGROK_URL=%%U"
    )
    if defined NGROK_URL (
      set "NGROK_READY=1"
    )
    if "!NGROK_READY!"=="0" timeout /t 1 >nul
  )
  if defined NGROK_URL (
    echo Ngrok URL: !NGROK_URL!
    if exist "%ENV_FILE%" (
      powershell -NoProfile -Command "$p='%ENV_FILE%'; $u='!NGROK_URL!'; $c=Get-Content $p -Raw; if($c -match '(?m)^ASR_AUDIO_PUBLIC_BASE_URL='){ $c=[regex]::Replace($c,'(?m)^ASR_AUDIO_PUBLIC_BASE_URL=.*$','ASR_AUDIO_PUBLIC_BASE_URL='+$u) } else { if(-not $c.EndsWith(\"`n\")){ $c += \"`n\" }; $c += 'ASR_AUDIO_PUBLIC_BASE_URL='+$u+\"`n\" }; Set-Content -Path $p -Value $c -Encoding UTF8"
      echo Updated backend/.env ASR_AUDIO_PUBLIC_BASE_URL
    )
  ) else (
    echo [WARN] ngrok URL not ready. AUC may fail until tunnel is available.
  )
) else (
  echo [WARN] ngrok executable not found: %NGROK_EXE%
)

echo [3/4] Starting Backend API...
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

echo [4/4] Starting Frontend Service...
for /f "tokens=1,2 delims=v." %%A in ('node -v 2^>nul') do set "NODE_MAJOR=%%B"
if not defined NODE_MAJOR (
  echo [WARN] Node.js not found. Frontend may fail to start.
) else (
  if %NODE_MAJOR% LSS 20 (
    echo [WARN] Current Node.js is too old for latest Vite. Please use Node 20.19+ or 22.12+.
  )
)
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
