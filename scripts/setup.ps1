# scripts/setup.ps1 - ClaudeBoost portable setup
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

$ErrorActionPreference = "Stop"

# Resolve ClaudeBoost install path from script location
$boostHome = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$claudeDir = Join-Path $env:USERPROFILE ".claude"

Write-Host "`n=== ClaudeBoost Setup ===" -ForegroundColor Cyan
Write-Host "ClaudeBoost home: $boostHome"
Write-Host "Claude config dir: $claudeDir`n"

# Ensure ~/.claude exists
if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir | Out-Null
    Write-Host "Created $claudeDir" -ForegroundColor Yellow
}

# --- 1. Create/update ~/.claude/mcp.json ---
$mcpPath = Join-Path $claudeDir "mcp.json"
$ragCwd = (Join-Path $boostHome "mcp-rag-server").Replace("\", "/")

$mcpConfig = @{
    mcpServers = @{
        "rag-server" = @{
            command = "python"
            args = @("-m", "rag_server")
            cwd = $ragCwd
        }
    }
}

$mcpJson = $mcpConfig | ConvertTo-Json -Depth 4
Set-Content -Path $mcpPath -Value $mcpJson -Encoding UTF8
Write-Host "[OK] mcp.json - RAG server registered globally" -ForegroundColor Green

# --- 2. Update ~/.claude/settings.json - add CLAUDEBOOST_HOME env ---
$settingsPath = Join-Path $claudeDir "settings.json"

if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
} else {
    Write-Host "[WARN] settings.json not found - creating minimal config" -ForegroundColor Yellow
    $settings = [PSCustomObject]@{}
}

# Ensure env block exists and add CLAUDEBOOST_HOME
if (-not $settings.PSObject.Properties["env"]) {
    $settings | Add-Member -NotePropertyName "env" -NotePropertyValue ([PSCustomObject]@{})
}
$boostHomePosix = $boostHome.Replace("\", "/")
if ($settings.env.PSObject.Properties["CLAUDEBOOST_HOME"]) {
    $settings.env.CLAUDEBOOST_HOME = $boostHomePosix
} else {
    $settings.env | Add-Member -NotePropertyName "CLAUDEBOOST_HOME" -NotePropertyValue $boostHomePosix
}

# Fix statusLine to use $TEMP instead of $LOCALAPPDATA/Temp
if ($settings.PSObject.Properties["statusLine"]) {
    $cmd = $settings.statusLine.command
    if ($cmd -and $cmd.Contains('$LOCALAPPDATA/Temp')) {
        $settings.statusLine.command = $cmd.Replace('$LOCALAPPDATA/Temp', '$TEMP')
        Write-Host "[OK] statusLine - fixed to use `$TEMP" -ForegroundColor Green
    }
}

# Add SessionStart hook if not present or replace orchestrator hook
$sessionHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "Check ~/.claude/CLAUDE.md decision flow: Is this a simple task (just do it) or complex (workspace + agents + RAG)? If complex: create workspace, call rag_search for relevant knowledge, spawn agents with rag_context."
            statusMessage = "Loading ClaudeBoost workflow..."
            timeout = 15
        }
    )
}

if (-not $settings.PSObject.Properties["hooks"]) {
    $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{})
}
if (-not $settings.hooks.PSObject.Properties["SessionStart"]) {
    $settings.hooks | Add-Member -NotePropertyName "SessionStart" -NotePropertyValue @($sessionHook)
    Write-Host "[OK] hooks.SessionStart - added lightweight workflow hook" -ForegroundColor Green
} else {
    Write-Host "[SKIP] hooks.SessionStart - already exists (review manually if needed)" -ForegroundColor Yellow
}

$settingsJson = $settings | ConvertTo-Json -Depth 10
Set-Content -Path $settingsPath -Value $settingsJson -Encoding UTF8
Write-Host "[OK] settings.json - CLAUDEBOOST_HOME env added" -ForegroundColor Green

# --- 3. Verify RAG server ---
Write-Host "`nVerifying RAG server..." -ForegroundColor Cyan
$ragDir = Join-Path $boostHome "mcp-rag-server"

try {
    # Always install from ClaudeBoost (editable mode) to ensure correct source path.
    Write-Host "Installing RAG server from $ragDir (editable mode)..." -ForegroundColor Cyan
    $pipOutput = & pip install -e $ragDir 2>&1
    $pipExitCode = $LASTEXITCODE
    if ($pipExitCode -ne 0) {
        Write-Host "[WARN] pip install returned exit code $pipExitCode" -ForegroundColor Yellow
        Write-Host ($pipOutput | Out-String) -ForegroundColor Yellow
    }

    # Verify it loads
    $loadPath = & python -c "import rag_server; print(rag_server.__file__)" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] RAG server installed: $loadPath" -ForegroundColor Green
    } else {
        Write-Host "[WARN] RAG server import failed after install" -ForegroundColor Yellow
        Write-Host "  Run manually: pip install -e $ragDir" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[WARN] Could not install RAG server: $_" -ForegroundColor Yellow
    Write-Host "  Run manually: pip install -e $ragDir" -ForegroundColor Yellow
}

# --- Summary ---
Write-Host "`n=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "  CLAUDEBOOST_HOME = $boostHomePosix"
Write-Host "  RAG server registered in $mcpPath"
Write-Host "  SessionStart hook configured"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Claude Code for MCP changes to take effect"
Write-Host "  2. Run /boost to verify all systems"
Write-Host "  3. (Optional) Rebuild Gas Town with 'make build' if gt errors occur"
Write-Host ""
