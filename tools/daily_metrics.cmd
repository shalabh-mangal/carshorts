@echo off
REM carshorts — daily EVALUATE step (metrics + learnings), no producing.
REM Pulls fresh YouTube analytics for every published video (updates recipe
REM cards), then folds them into learnings so the NEXT car starts smarter.
REM Gate 1/2 stay manual — this job never renders or publishes.
REM Scheduled via tools\schedule_daily_metrics.cmd (Windows Task Scheduler).

chcp 65001 >nul
cd /d "%~dp0.."
set PYTHONUTF8=1

echo [%date% %time%] refreshing YouTube analytics (retention-watch)...
".venv\Scripts\python.exe" -m carshorts retention-watch

echo [%date% %time%] folding metrics into learnings (analyze)...
".venv\Scripts\python.exe" -m carshorts analyze

echo [%date% %time%] daily evaluate complete.
