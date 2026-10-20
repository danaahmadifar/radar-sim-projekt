@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m radar_sim
) else (
    python -m radar_sim
)
if errorlevel 1 pause
