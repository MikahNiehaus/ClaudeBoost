@echo off
REM Start the clean-rag server in a visible window so you can watch the logs.
REM Safe to run twice. server_ctl checks the port and refuses to start a second one.

cd /d "%~dp0"

echo Starting clean-rag server...
python cli\server_ctl.py start

echo.
echo If a server was already running, nothing was started (that is intended).
echo Close the server's own console window to stop it, or run: python cli\server_ctl.py stop
echo.
pause
