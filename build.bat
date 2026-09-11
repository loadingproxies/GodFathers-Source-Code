@echo off
cd /d "%~dp0"
title GodFathers OCR — build exe

if not exist ".venv\Scripts\python.exe" (
  echo Run "Start GodFathers OCR.bat" once first so Python packages are installed.
  echo Then run this file again.
  pause
  exit /b 1
)

echo Installing PyInstaller if needed...
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.0"
if errorlevel 1 (
  echo Could not install PyInstaller.
  pause
  exit /b 1
)

echo.
echo Building the exe. This can take several minutes.
echo.
".venv\Scripts\python.exe" tools\build_exe.py
if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo Send dist\GodFathers-OCR-windows.zip
echo Friends unzip it and double-click GodFathersOCR.exe
echo.
pause
