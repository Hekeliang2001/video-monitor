@echo off
setlocal

cd /d "%~dp0"

set "VIDEO_MONITOR_HOST=127.0.0.1"
set "VIDEO_MONITOR_PORT=8000"

if not "%~1"=="" set "VIDEO_MONITOR_PORT=%~1"

if exist "dist\VideoMonitorConsole.exe" (
  "dist\VideoMonitorConsole.exe"
) else if exist "VideoMonitorConsole.exe" (
  "VideoMonitorConsole.exe"
) else (
  echo VideoMonitorConsole.exe was not found.
  echo Run build_windows_exe.bat or build_windows_standalone_exe.bat first.
  pause
  exit /b 1
)

pause
