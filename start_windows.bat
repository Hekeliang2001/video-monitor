@echo off
setlocal

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8000"

if not "%~1"=="" set "PORT=%~1"
set "VIDEO_MONITOR_HOST=%HOST%"
set "VIDEO_MONITOR_PORT=%PORT%"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment was not found.
  echo Run install_windows.bat first.
  pause
  exit /b 1
)

echo Starting video control panel...
echo.
echo Keep this window open while using the control panel.
echo Press Ctrl+C in this window to stop the service.
echo.

".venv\Scripts\python.exe" launcher.py

pause
