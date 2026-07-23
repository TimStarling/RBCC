@echo off
cd /d "%~dp0"
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js is not installed or is not in PATH.
  pause
  exit /b 1
)
start "TCP HTML Client" cmd /k "node server.js"
timeout /t 1 /nobreak >nul
start "" "http://127.0.0.1:3000"
