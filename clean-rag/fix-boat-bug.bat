@echo off
REM fix-boat-bug.bat
REM Stops the RAG server, removes bloated ChromaDB databases, restarts the server.
REM Runs with --force by default (no prompts). Safe: only deletes index data inside
REM this ClaudeBoost directory — never touches your actual project files.
REM
REM Usage:
REM   clean-rag\fix-boat-bug.bat              :: full cleanup, no prompts (default)
REM   clean-rag\fix-boat-bug.bat --dry-run    :: report only, no deletions

setlocal

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found on PATH. Install Python 3.9+ first.
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM Step 1: Stop the RAG server (releases SQLite file handles)
REM ---------------------------------------------------------------------------
echo.
echo [1/3] Stopping RAG server...

python "%SCRIPT_DIR%\cli\server_ctl.py" stop >nul 2>&1

REM Kill any process still holding the server port. Honours CLEAN_RAG_PORT so a
REM machine running the server on a non default port still gets cleaned up;
REM hardcoding 8613 left the real process alive and the next start silently reused it.
if "%CLEAN_RAG_PORT%"=="" set "CLEAN_RAG_PORT=8613"
python -c "import os,subprocess; port=os.environ.get('CLEAN_RAG_PORT','8613'); r=subprocess.run(['netstat','-ano'],capture_output=True,text=True); pids=[l.strip().split()[-1] for l in r.stdout.splitlines() if (':'+port) in l and 'LISTENING' in l]; [subprocess.run(['taskkill','/PID',p,'/F'],capture_output=True) or print('  Killed PID '+p) for p in pids] if pids else print('  No process on port '+port)"

timeout /t 2 /nobreak >nul
echo   Done.
echo.

REM ---------------------------------------------------------------------------
REM Step 2: Delete bloated databases
REM ---------------------------------------------------------------------------
echo [2/3] Scanning and cleaning bloated databases...
echo.

REM Check for --dry-run flag
echo %* | findstr /i "dry-run" >nul
if %ERRORLEVEL% equ 0 (
    python "%SCRIPT_DIR%\fix_boat_bug.py"
    goto restart
)

python "%SCRIPT_DIR%\fix_boat_bug.py" --force
echo.

REM ---------------------------------------------------------------------------
REM Step 3: Restart the RAG server
REM ---------------------------------------------------------------------------
:restart
echo [3/3] Restarting RAG server...
python "%SCRIPT_DIR%\cli\server_ctl.py" start
echo.
echo Done. Re-index any deleted projects with /index-project ^<path^>

endlocal
