@echo off
REM Start the clean-rag server, windowless, with the live console UI beside it.
REM
REM CLEAN_RAG_HEADED is deliberately NOT set here any more. It gave the server
REM its own raw terminal, and server_ctl now opens cli\console.py in its own
REM window on every start, so setting it would produce two windows showing the
REM same log. The console is the better of the two: it renders indexing state
REM and lets you pause sweeps, and closing it cannot kill the server, which a
REM headed server's window could and did on 2026-09-18.
REM
REM Safe to run twice. server_ctl checks the port and refuses to start a second
REM server, and still opens the console so you are not left with no UI.

cd /d "%~dp0"

echo Starting clean-rag server...
python cli\server_ctl.py start

echo.
echo The console UI opens in its own window. The server itself has none.
echo The model takes about a minute to load; the console shows that happening.
echo.
echo To stop the server: python cli\server_ctl.py stop
echo Closing the console window leaves the server running.
echo To start with no UI at all: set CLEAN_RAG_CONSOLE=0
echo.
pause
