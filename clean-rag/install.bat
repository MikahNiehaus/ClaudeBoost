@echo off
REM clean-rag installer (Windows)
REM Usage:
REM   clean-rag\install.bat                     :: full install with pre-seeding
REM   clean-rag\install.bat --no-seed           :: skip pre-seeding (fast)
REM   clean-rag\install.bat --seed react,fastapi :: seed specific topics
REM   clean-rag\install.bat --skip-deps         :: skip pip install

setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found. Install Python 3.10+ and try again.
    exit /b 1
)

python --version
python "%SCRIPT_DIR%install.py" %*
