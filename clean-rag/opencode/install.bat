@echo off
REM clean-rag OpenCode integration installer (Windows)
REM
REM KEEP IN SYNC WITH install.sh. Both just find a Python interpreter and exec
REM install.py, so the real logic lives in install.py. Change one, change the other.
REM
REM Usage:
REM   clean-rag\opencode\install.bat

setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Install Python 3.10+ and try again.
    exit /b 1
)

python --version
python "%SCRIPT_DIR%install.py" %*
