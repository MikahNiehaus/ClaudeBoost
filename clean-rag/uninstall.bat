@echo off
REM clean-rag uninstaller (Windows)
REM Usage:
REM   clean-rag\uninstall.bat            :: remove hooks + env, keep data
REM   clean-rag\uninstall.bat --purge    :: also delete databases/ and state/

setlocal

set "SCRIPT_DIR=%~dp0"

where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Python not found.
    exit /b 1
)

python "%SCRIPT_DIR%uninstall.py" %*
