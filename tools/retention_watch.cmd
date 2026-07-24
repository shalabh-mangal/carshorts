@echo off
REM Daily retention watch - polls YouTube for per-second retention curves and,
REM the moment one appears, maps the drop-offs onto that video's script beats.
REM Registered as Windows Scheduled Task "carshorts-retention-watch".
REM Machine-specific - assumes the venv at .venv in the repo root.

chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1

if not exist "data\logs" mkdir "data\logs"
".venv\Scripts\python.exe" -m carshorts.retention_watch >> "data\logs\retention_watch.log" 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> "data\logs\retention_watch.log"
