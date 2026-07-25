@echo off
REM Daily heartbeat - runs the day: refresh analytics, decide, draft the next
REM calendar slot, write an owner report. NEVER publishes (both gates are the
REM owner's). Registered as Windows Scheduled Task "carshorts-heartbeat".
REM ffmpeg is expected on PATH (setup.ps1 puts it there); no machine-specific
REM path is hardcoded, so this wrapper is portable to a fresh machine.

chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1

if not exist "data\logs" mkdir "data\logs"
".venv\Scripts\python.exe" -m carshorts heartbeat >> "data\logs\heartbeat.log" 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> "data\logs\heartbeat.log"
