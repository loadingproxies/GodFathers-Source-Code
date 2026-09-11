@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" tools\build_share.py
) else (
  echo Run "Start GodFathers OCR.bat" once first, then run this again.
)
echo.
echo The zip is in the dist folder. Send GodFathers-OCR-share.zip
echo Do not send your .venv, logs, or config\clicks.json
pause
