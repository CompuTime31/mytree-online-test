@echo off
setlocal
cd /d "%~dp0"
title MyTree Professional RC16.18.2 - Reset Demo
where py >nul 2>&1
if %errorlevel%==0 (
  py demo_mode.py --reset
) else (
  python demo_mode.py --reset
)
pause
