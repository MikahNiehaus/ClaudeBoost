# fix-hooks.ps1 — Emergency hook repair
#
# Removes any hook entries whose command string contains a literal $CLAUDEBOOST_HOME
# bash variable reference. These block Claude Code prompts on machines where
# CLAUDEBOOST_HOME has not been configured in settings.json yet.
#
# Run this BEFORE setup.ps1 when Claude Code is completely blocked:
#   powershell -ExecutionPolicy Bypass -File "C:\Development\ClaudeBoost\scripts\fix-hooks.ps1"
#
# No prerequisites — does NOT require CLAUDEBOOST_HOME, Python, or Claude Code.

$settingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"

Write-Host "`n=== ClaudeBoost Hook Repair ===" -ForegroundColor Cyan
Write-Host "Settings: $settingsPath`n"

if (-not (Test-Path $settingsPath)) {
    Write-Host "[ERROR] settings.json not found at $settingsPath" -ForegroundColor Red
    exit 1
}

try {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
} catch {
    Write-Host "[ERROR] settings.json is malformed JSON: $_" -ForegroundColor Red
    Write-Host "  Fix the JSON manually then re-run this script." -ForegroundColor Red
    exit 1
}

if (-not $settings.PSObject.Properties["hooks"]) {
    Write-Host "[OK] No hooks block found — nothing to fix." -ForegroundColor Green
    exit 0
}

$removed = 0
foreach ($hookType in @($settings.hooks.PSObject.Properties.Name)) {
    $entries = @($settings.hooks.$hookType)
    $cleaned  = @()
    foreach ($entry in $entries) {
        $isStale = $false
        if ($entry.hooks) {
            foreach ($h in @($entry.hooks)) {
                if ($h.command -and $h.command -like '*$CLAUDEBOOST_HOME*') {
                    $preview = $h.command.Substring(0, [Math]::Min(72, $h.command.Length))
                    Write-Host "[REMOVE] hooks.$hookType : $preview" -ForegroundColor Yellow
                    $isStale = $true
                    $removed++
                    break
                }
            }
        }
        if (-not $isStale) { $cleaned += $entry }
    }
    $settings.hooks.$hookType = $cleaned
}

if ($removed -eq 0) {
    Write-Host "[OK] No stale `$CLAUDEBOOST_HOME variable hooks found — nothing to fix." -ForegroundColor Green
    exit 0
}

$json = $settings | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($settingsPath, $json, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "[OK] Removed $removed stale hook(s) from settings.json" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run full setup:  powershell -ExecutionPolicy Bypass -File `"$(Split-Path $PSScriptRoot -Parent)\scripts\setup.ps1`""
Write-Host "  2. Restart Claude Code"
