@echo off
setlocal EnableExtensions

cd /d "%~dp0"

set "PYTHON_VERSION=3.12.10"
set "LOCAL_PY_DIR=%CD%\.build-python"
set "LOCAL_PY_EXE=%LOCAL_PY_DIR%\python.exe"
set "LOCAL_TEMP_DIR=%CD%\.temp"
set "LOCAL_PIP_CACHE_DIR=%CD%\.pip-cache"
set "PYTHON_INSTALLER=%LOCAL_TEMP_DIR%\video-monitor-python-%PYTHON_VERSION%-amd64.exe"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-amd64.exe"
set "PY_EXE="
set "PY_ARGS="
set "FOUND_PY="
set "FOUND_PYTHON="

if not exist "%LOCAL_TEMP_DIR%" mkdir "%LOCAL_TEMP_DIR%"
if not exist "%LOCAL_PIP_CACHE_DIR%" mkdir "%LOCAL_PIP_CACHE_DIR%"
set "TEMP=%LOCAL_TEMP_DIR%"
set "TMP=%LOCAL_TEMP_DIR%"
set "PIP_CACHE_DIR=%LOCAL_PIP_CACHE_DIR%"

if exist "%LOCAL_PY_EXE%" (
  set "PY_EXE=%LOCAL_PY_EXE%"
  goto python_ready
)

for /f "delims=" %%I in ('where py 2^>nul') do (
  set "FOUND_PY=%%I"
  goto check_py_launcher
)

:check_python
for /f "delims=" %%I in ('where python 2^>nul') do (
  set "FOUND_PYTHON=%%I"
  goto check_python_exe
)
goto download_python

:check_py_launcher
"%FOUND_PY%" -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PY_EXE=%FOUND_PY%"
  set "PY_ARGS=-3"
  goto python_ready
)
goto check_python

:check_python_exe
"%FOUND_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PY_EXE=%FOUND_PYTHON%"
  goto python_ready
)

:download_python
echo Python 3 was not found.
echo Downloading local build Python %PYTHON_VERSION%...

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"
if %ERRORLEVEL% NEQ 0 (
  echo Failed to download Python installer.
  echo Please check the network connection, then run this script again.
  endlocal
  exit /b 1
)

echo Installing local build Python...
start /wait "" "%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 TargetDir="%LOCAL_PY_DIR%" Include_launcher=0 PrependPath=0 Include_pip=1 Include_venv=1 Include_test=0
if %ERRORLEVEL% NEQ 0 (
  echo Failed to install local build Python.
  endlocal
  exit /b 1
)

if not exist "%LOCAL_PY_EXE%" (
  echo Local build Python was not found after installation.
  endlocal
  exit /b 1
)

set "PY_EXE=%LOCAL_PY_EXE%"

:python_ready
"%PY_EXE%" %PY_ARGS% -c "import sys; print(sys.version); raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if %ERRORLEVEL% NEQ 0 (
  echo Python exists but cannot run, or the version is older than 3.10.
  endlocal
  exit /b 1
)

endlocal & set "PY_EXE=%PY_EXE%" & set "PY_ARGS=%PY_ARGS%" & set "TEMP=%LOCAL_TEMP_DIR%" & set "TMP=%LOCAL_TEMP_DIR%" & set "PIP_CACHE_DIR=%LOCAL_PIP_CACHE_DIR%"
exit /b 0
