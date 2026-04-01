@echo off
setlocal
set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "BACKEND_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"

cd /d "%BACKEND_DIR%"
if not exist "%BACKEND_PY%" (
  echo [ERROR] Backend Python not found: %BACKEND_PY%
  echo Please recreate backend virtual env first.
  pause
  exit /b 1
)

echo Starting backend at http://127.0.0.1:8000 ...
"%BACKEND_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
