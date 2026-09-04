@echo off
rem ===== DocMind one-click start script (double-click to run) =====
rem No conda activate needed; calls the docmind env python directly.
rem Edit the python path below if you move your conda environment.
chcp 65001 >nul
cd /d %~dp0
%USERPROFILE%\.conda\envs\docmind\python.exe -X utf8 -m uvicorn app.main:app --port 8000 --reload
echo.
echo If you see an error above (e.g. port 8000 already in use),
echo the server did NOT start. Keep this window open and ask for help.
pause
