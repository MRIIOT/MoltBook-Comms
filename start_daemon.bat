@echo off
echo Starting Moltbook Daemon ...
echo Press Ctrl+C to stop
echo.
cd /d "%~dp0"
python moltbook_daemon.py
pause
