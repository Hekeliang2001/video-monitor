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

echo Upgrading pip...
python -m pip install --upgrade pip
if %ERRORLEVEL% NEQ 0 (
  echo Failed to upgrade pip.
  pause
  exit /b 1
)

echo Installing Python dependencies...
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

echo.
echo Installation completed.
echo This build uses installed Microsoft Edge or Google Chrome. No Playwright Chromium download is required.
echo Run start_windows.bat to open the control panel.
pause
