@echo off

:: Remember where we started
set "SRCDIR=%CD%"

:: Get the current directory name as the rig name
for %%I in ("%SRCDIR%") do set "RIGNAME=%%~nxI"
set "RIGNAME=%RIGNAME: =-%"

:: Check if this is already a rig — fast path
if exist "%USERPROFILE%\gt\%RIGNAME%\crew\mikah" (
    echo Opening crew workspace for %RIGNAME%...
    cd /d "%USERPROFILE%\gt\%RIGNAME%\crew\mikah"
    echo.
    echo ========================================
    echo   Session Options
    echo ========================================
    echo   [1] New session
    echo   [2] Continue most recent session
    echo   [3] Resume (pick from list)
    echo ========================================
    echo.
    set /p "CHOICE=Choose [1/2/3]: "
    if "%CHOICE%"=="2" (
        claude --continue "gt prime"
    ) else if "%CHOICE%"=="3" (
        claude --resume
    ) else (
        claude "gt prime"
    )
    exit /b
)

:: Not a rig yet — set it up
echo ========================================
echo   Setting up %RIGNAME% as a Gastown rig
echo ========================================
echo.

:: Step 1: Ensure Dolt is running FIRST
echo [1/6] Ensuring Dolt server is running...
cd /d "%USERPROFILE%\gt"
gt dolt recover >nul 2>&1
gt dolt status 2>nul | findstr /c:"running" >nul || (
    gt dolt start
)

:: Step 2: Go back to source and ensure it's a git repo
cd /d "%SRCDIR%"
if not exist ".git" (
    echo [2/6] Initializing git repo...
    git init
    git add -A
    git commit -m "initial commit" --allow-empty
) else (
    echo [2/6] Git repo found.
)

:: Step 3: Check for remote
set "REMOTE="
for /f "delims=" %%R in ('git remote get-url origin 2^>nul') do set "REMOTE=%%R"

:: Step 4: Add rig
cd /d "%USERPROFILE%\gt"
if "%REMOTE%"=="" (
    echo [3/6] No remote found. Adopting local project...
    if not exist "%USERPROFILE%\gt\%RIGNAME%" (
        xcopy /E /I /Q "%SRCDIR%" "%USERPROFILE%\gt\%RIGNAME%" >nul 2>&1
    )
    gt rig add %RIGNAME% --adopt --force
) else (
    echo [3/6] Adding rig from remote: %REMOTE%
    gt rig add %RIGNAME% %REMOTE%
)

if errorlevel 1 (
    echo ERROR: Failed to add rig.
    exit /b 1
)

:: Step 5: Restart Dolt to pick up new database, then init beads
echo [4/6] Restarting Dolt for new database...
gt dolt stop 2>nul
ping -n 3 127.0.0.1 >nul
gt dolt start

echo [5/6] Initializing beads...
set "PREFIX=%RIGNAME:~0,2%"
cd /d "%USERPROFILE%\gt\%RIGNAME%"
bd init --force --prefix %PREFIX% 2>nul

:: Step 6: Create crew workspace
echo [6/6] Creating crew workspace...
cd /d "%USERPROFILE%\gt"

:: Try gt crew add first (works for rigs with remotes)
gt crew add mikah --rig %RIGNAME% 2>nul
if errorlevel 1 (
    :: For adopted local rigs without remotes, create crew manually
    echo Creating crew workspace manually for local rig...
    mkdir "%USERPROFILE%\gt\%RIGNAME%\crew\mikah" 2>nul
    cd /d "%USERPROFILE%\gt\%RIGNAME%\crew\mikah"
    xcopy /E /I /Q "%SRCDIR%" "." >nul 2>&1
    mkdir ".claude" 2>nul
)

gt hooks sync >nul 2>&1
gt doctor --fix --no-start >nul 2>&1

echo.
echo ========================================
echo   Ready! Launching Claude Code...
echo   Rig: %RIGNAME%
echo   Workspace: %USERPROFILE%\gt\%RIGNAME%\crew\mikah
echo ========================================
echo.
cd /d "%USERPROFILE%\gt\%RIGNAME%\crew\mikah"
echo.
echo ========================================
echo   Session Options
echo ========================================
echo   [1] New session
echo   [2] Continue most recent session
echo   [3] Resume (pick from list)
echo ========================================
echo.
set /p "CHOICE=Choose [1/2/3]: "
if "%CHOICE%"=="2" (
    claude --continue "gt prime"
) else if "%CHOICE%"=="3" (
    claude --resume
) else (
    claude "gt prime"
)
