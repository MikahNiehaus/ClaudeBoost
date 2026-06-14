@echo off
setlocal enabledelayedexpansion

echo.
echo  ClaudeBoost Uninstaller
echo  =======================
echo.
echo  Reverses install.bat / setup.py: hooks, env, statusLine, permissions,
echo  the .claude symlinks/helpers, the rag-server MCP entry, and the RAG server.
echo.
echo  Default removes only ClaudeBoost's footprint. Pass --purge for the heavier
echo  shared bits, or --dry-run to preview without changing anything.
echo.

:: Directory this script lives in (ClaudeBoost root)
set "BOOST_DIR=%~dp0"
set "BOOST_DIR=%BOOST_DIR:~0,-1%"

:: Pick a Python launcher
where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
        set "PY=py"
    ) else (
        echo ERROR: python not found on PATH. Install Python 3.9+ first.
        exit /b 1
    )
)

%PY% "%BOOST_DIR%\scripts\uninstall.py" %*

endlocal
