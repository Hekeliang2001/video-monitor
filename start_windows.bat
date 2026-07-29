@echo off
setlocal

cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8000"

if not "%~1"=="" set "PORT=%~1"

if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment was not found.
  echo Run install_windows.bat first.
  pause
  exit /b 1
)

echo Starting video control panel...
echo URL: http://%HOST%:%PORT%/
echo.
echo Keep this window open while using the control panel.
echo Press Ctrl+C in this window to stop the service.
echo.

start "" "http://%HOST%:%PORT%/"
".venv\Scripts\python.exe" -m uvicorn web_app:app --host %HOST% --port %PORT%

pause
