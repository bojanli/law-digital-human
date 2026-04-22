@echo off
title Stopping Law Digital Human Background Services

echo ===================================================
echo Stopping Background Services...
echo ===================================================

echo [1/3] Stopping Node (Frontend)...
taskkill /F /IM node.exe /T

echo [2/3] Stopping Python (Backend uvicorn)...
taskkill /F /IM python.exe /T

echo [3/3] Stopping Docker Hub (Optional, skipped by default)
:: docker-compose down

echo.
echo All background services stopped!
echo ===================================================
pause
