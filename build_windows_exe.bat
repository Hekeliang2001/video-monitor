@echo off
setlocal

cd /d "%~dp0"

call "%~dp0ensure_windows_python.bat"
if %ERRORLEVEL% NEQ 0 (
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  "%PY_EXE%" %PY_ARGS% -m venv .venv
  if %ERRORLEVEL% NEQ 0 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"

echo Installing build dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if %ERRORLEVEL% NEQ 0 (
  echo Failed to install build dependencies.
  pause
  exit /b 1
)

echo Building VideoMonitorConsole.exe...
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --console ^
  --name VideoMonitorConsole ^
  --add-data "web;web" ^
  --collect-all playwright ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import uvicorn.loops.asyncio ^
  --hidden-import uvicorn.protocols.http.h11_impl ^
  launcher.py

if %ERRORLEVEL% NEQ 0 (
  echo Failed to build exe.
  pause
  exit /b 1
)

echo.
echo Build completed:
echo dist\VideoMonitorConsole.exe
echo.
echo Double-click dist\VideoMonitorConsole.exe to start the control panel.
echo This exe uses installed Microsoft Edge or Google Chrome. No Playwright Chromium download is required.
pause
