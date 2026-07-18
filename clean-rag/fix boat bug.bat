@echo off
REM fix boat bug.bat — detect and remove bloated ChromaDB project databases
REM
REM Usage:
REM   clean-rag\fix boat bug.bat           :: report only, prompt per project
REM   clean-rag\fix boat bug.bat --force   :: delete all bloated without prompting
REM
REM All deletions happen inside clean-rag\databases\_projects\ only.
REM Nothing outside this ClaudeBoost directory is touched.

setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found.
    exit /b 1
)

python "%SCRIPT_DIR%fix_boat_bug.py" %*
