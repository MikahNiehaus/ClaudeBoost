@echo off
REM clean-rag installer (Windows)
REM
REM KEEP IN SYNC WITH install.sh: this is the Windows twin of the
REM Linux/macOS installer. Both just find a Python interpreter and exec
REM install.py with the same args, so the real logic lives in install.py --
REM but if you change flag handling, usage text, or the Python-detection
REM fallback order here, make the matching change in install.sh too (and
REM vice versa), or the two platforms will drift out of sync silently.
REM
REM Usage:
REM   clean-rag\install.bat                :: full install (idempotent, safe to re-run)
REM   clean-rag\install.bat --skip-deps    :: skip pip install

setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Install Python 3.10+ and try again.
    exit /b 1
)

python --version
python "%SCRIPT_DIR%install.py" %*
