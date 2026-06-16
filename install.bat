@echo off
setlocal enabledelayedexpansion

echo.
echo  ClaudeBoost Installer
echo  =====================
echo.
echo  Installs ClaudeBoost globally so every project has access to
echo  agents, knowledge bases, RAG search, and slash commands.
echo.

:: Directory this script lives in (ClaudeBoost root)
set "BOOST_DIR=%~dp0"
set "BOOST_DIR=%BOOST_DIR:~0,-1%"
set "CLAUDE_DIR=%USERPROFILE%\.claude"

echo  Source:  %BOOST_DIR%
echo  Target:  %CLAUDE_DIR%
echo.

:: ── Find Python ──────────────────────────────────────────────────────────────
set "PY="
where python >nul 2>&1 && set "PY=python"
if not defined PY (
    where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
    echo  ERROR: Python not found on PATH. Install Python 3.9+ first.
    exit /b 1
)

if not exist "%CLAUDE_DIR%" (
    mkdir "%CLAUDE_DIR%"
    if errorlevel 1 (
        echo  ERROR: Could not create %CLAUDE_DIR%. Check permissions.
        exit /b 1
    )
)

:: ── 1. Link CLAUDE.md ────────────────────────────────────────────────────────
echo  [1/3] Linking CLAUDE.md...

if exist "%CLAUDE_DIR%\CLAUDE.md" del "%CLAUDE_DIR%\CLAUDE.md" >nul 2>&1
mklink /h "%CLAUDE_DIR%\CLAUDE.md" "%BOOST_DIR%\CLAUDE.md" >nul 2>&1
if errorlevel 1 (
    :: mklink requires Developer Mode on some Windows configs. Fall back to copy.
    copy /y "%BOOST_DIR%\CLAUDE.md" "%CLAUDE_DIR%\CLAUDE.md" >nul 2>&1
    if errorlevel 1 (
        echo  ERROR: Could not link or copy CLAUDE.md. Check permissions.
        exit /b 1
    )
    echo        CLAUDE.md copied (re-run install.bat after git pull to update it).
) else (
    echo        CLAUDE.md linked (auto-updates on git pull).
)

:: ── 2. Link slash commands ───────────────────────────────────────────────────
echo  [2/3] Linking slash commands...

:: Remove existing directory or junction so we can recreate it.
:: rmdir without /s removes junctions without touching the target.
:: If commands is a real non-empty directory, rmdir fails silently and we skip.
if exist "%CLAUDE_DIR%\commands" (
    rmdir "%CLAUDE_DIR%\commands" >nul 2>&1
)
if not exist "%CLAUDE_DIR%\commands" (
    mklink /j "%CLAUDE_DIR%\commands" "%BOOST_DIR%\.claude\commands" >nul 2>&1
    if errorlevel 1 (
        echo        Could not create junction. setup.py will copy commands instead.
    ) else (
        echo        Slash commands linked (junction — auto-updates on git pull).
    )
) else (
    echo        Existing commands directory could not be removed. setup.py will copy commands instead.
)

:: ── 3. Run setup.py ──────────────────────────────────────────────────────────
echo  [3/3] Running setup.py (hooks, RAG server, MCP tools, permissions)...
echo.

%PY% "%BOOST_DIR%\scripts\setup.py"
if errorlevel 1 (
    echo.
    echo  [ERROR] setup.py reported issues. Review the output above,
    echo          fix them, then re-run install.bat.
    pause
    exit /b 1
)

:: Count slash commands for the summary
set CMD_COUNT=0
for /f %%i in ('dir /b /a-d "%BOOST_DIR%\.claude\commands\*.md" 2^>nul ^| find /c /v ""') do set CMD_COUNT=%%i

echo.
echo  ============================================================
echo   ClaudeBoost installed!
echo.
echo   %CMD_COUNT% slash commands available in every Claude Code session.
echo.
echo   Next: open Claude Code and run:
echo     /boost
echo.
echo   /boost checks all systems and auto-fixes anything still off.
echo  ============================================================
echo.

endlocal
