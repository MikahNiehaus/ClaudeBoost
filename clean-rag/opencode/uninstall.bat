@echo off
REM clean-rag OpenCode integration uninstaller (Windows)
REM
REM KEEP IN SYNC WITH uninstall.sh. Both just find Python and exec uninstall.py.
REM
REM Usage:
REM   clean-rag\opencode\uninstall.bat

setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found.
    exit /b 1
)

python "%SCRIPT_DIR%uninstall.py" %*
