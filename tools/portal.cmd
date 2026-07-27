@echo off
REM Review portal - the Gate 1 / Gate 2 review station at http://localhost:8787.
REM It's a LOCAL server (no hosting), so it's only "up" while this window is open.
REM Double-click to launch; it opens your browser and stays running. Ctrl-C to stop.
REM ffmpeg is expected on PATH (setup.ps1 puts it there); no machine-specific path
REM is hardcoded, so this wrapper is portable to a fresh machine.

chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1

echo Review station -> http://localhost:8787   (leave this window open; Ctrl-C to stop)
start "" http://localhost:8787
".venv\Scripts\python.exe" -m carshorts portal
