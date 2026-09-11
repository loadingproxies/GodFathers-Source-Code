@echo off
setlocal
cd /d "%~dp0"
title GodFathers OCR

echo.
echo GodFathers OCR
echo First run installs what is needed. That can take a few minutes.
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"

if not defined PY (
  echo Python was not found. Installing Python 3.12...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo Could not install Python. Install Python 3.12 from https://www.python.org/downloads/
    echo Tick "Add python.exe to PATH", then run this file again.
    pause
    exit /b 1
  )
  set "PY=py -3"
)

%PY% tools\setup_windows.py
if errorlevel 1 (
  echo Setup failed.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\pythonw.exe" (
  echo Setup did not create .venv\Scripts\pythonw.exe
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "main.py"
endlocal
