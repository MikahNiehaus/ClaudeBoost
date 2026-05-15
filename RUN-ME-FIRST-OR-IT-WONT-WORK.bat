@echo off
setlocal enabledelayedexpansion

set "BOOST_DIR=%~dp0"
set "BOOST_DIR=%BOOST_DIR:~0,-1%"

echo.
echo  ClaudeBoost
echo  ===========
echo  Run this once after cloning to get fully set up.
echo.
echo  What this does:
echo    1. Runs PowerShell setup (installs RAG server, hooks, MCP config)
echo    2. Opens Claude Code and runs /setup to verify everything
echo.
pause

:: ── Step 1: PowerShell setup ──────────────────────────────────────────────
echo.
echo [1/2] Running setup...
echo.
powershell -ExecutionPolicy Bypass -File "%BOOST_DIR%\scripts\setup.ps1"

if errorlevel 1 (
    echo.
    echo  [ERROR] Setup failed. Fix the issues shown above, then re-run this file.
    pause
    exit /b 1
)

:: ── Step 2: Open Claude Code with /setup to verify ────────────────────────
echo.
echo [2/2] Opening Claude Code...
echo       Claude will run /setup automatically to verify all systems.
echo.
cd /d "%BOOST_DIR%"
claude "/setup"

endlocal
