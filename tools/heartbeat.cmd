@echo off
REM Daily heartbeat - runs the day: refresh analytics, decide, draft the next
REM calendar slot, write an owner report. NEVER publishes (both gates are the
REM owner's). Registered as Windows Scheduled Task "carshorts-heartbeat".

chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1
set PATH=C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin;%PATH%

if not exist "data\logs" mkdir "data\logs"
".venv\Scripts\python.exe" -m carshorts.heartbeat >> "data\logs\heartbeat.log" 2>&1
echo [%date% %time%] exit=%ERRORLEVEL% >> "data\logs\heartbeat.log"
