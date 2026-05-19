# fix-hooks.ps1 - Emergency hook repair
#
# Removes hook entries that are known to block Claude Code prompts:
#   1. Commands containing a literal $CLAUDEBOOST_HOME bash variable reference
#      (set by older setup versions; fail when CLAUDEBOOST_HOME is not in env block)
#   2. Commands referencing a ClaudeBoost script path that no longer exists on disk
#      (e.g. ensure-setup.py from a different machine where ClaudeBoost is at a different path)
#
# Run this BEFORE setup.ps1 when Claude Code is completely blocked:
#   powershell -ExecutionPolicy Bypass -File "C:\Development\ClaudeBoost\scripts\fix-hooks.ps1"
#
# No prerequisites - does NOT require CLAUDEBOOST_HOME, Python, or Claude Code.

$settingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"

Write-Host "`n=== ClaudeBoost Hook Repair ===" -ForegroundColor Cyan
Write-Host "Settings: $settingsPath`n"

if (-not (Test-Path $settingsPath)) {
    Write-Host "[OK] settings.json not found - fresh install, nothing to fix." -ForegroundColor Green
    exit 0
}

try {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
} catch {
    Write-Host "[ERROR] settings.json is malformed JSON: $_" -ForegroundColor Red
    Write-Host "  Fix the JSON manually then re-run this script." -ForegroundColor Red
    exit 1
}

if (-not $settings.PSObject.Properties["hooks"]) {
    Write-Host "[OK] No hooks block found - nothing to fix." -ForegroundColor Green
    exit 0
}

function Test-HookStale {
    param([string] $Command)
    # Pattern 1: literal $CLAUDEBOOST_HOME bash variable
    if ($Command -like '*$CLAUDEBOOST_HOME*') { return $true }
    # Pattern 2: python "C:/some/absolute/path/script.py" where that path doesn't exist
    $m = [regex]::Match($Command, 'python\s+"([^"]+\.py)"')
    if ($m.Success) {
        $scriptPath = $m.Groups[1].Value -replace '/', '\'
        if (-not (Test-Path $scriptPath)) { return $true }
    }
    return $false
}

$removed = 0
foreach ($hookType in @($settings.hooks.PSObject.Properties.Name)) {
    $entries    = @($settings.hooks.$hookType)
    $newEntries = @()

    foreach ($entry in $entries) {
        if ($entry.hooks) {
            # Filter individual stale hooks; keep entry if any healthy hooks remain
            $healthyHooks = @()
            foreach ($h in @($entry.hooks)) {
                if ($h.command -and (Test-HookStale $h.command)) {
                    $preview = $h.command.Substring(0, [Math]::Min(72, $h.command.Length))
                    Write-Host "[REMOVE] hooks.$hookType : $preview" -ForegroundColor Yellow
                    $removed++
                } else {
                    $healthyHooks += $h
                }
            }
            if ($healthyHooks.Count -gt 0) {
                $entry.hooks = $healthyHooks
                $newEntries += $entry
            }
            # If all hooks in this entry were stale, drop the whole entry (no healthy siblings)
        } else {
            $newEntries += $entry
        }
    }

    if ($newEntries.Count -gt 0) {
        $settings.hooks.$hookType = $newEntries
    } else {
        $settings.hooks.PSObject.Properties.Remove($hookType)
    }
}

# Also clean up the sentinel file so ensure-setup.py can re-trigger after repair
$sentinelPath = Join-Path $env:USERPROFILE ".claude\.ensure-setup-triggered"
if (Test-Path $sentinelPath) {
    Remove-Item $sentinelPath -Force
    Write-Host "[OK] Cleared ensure-setup sentinel" -ForegroundColor Green
}

if ($removed -eq 0) {
    Write-Host "[OK] No stale hooks found - nothing to fix." -ForegroundColor Green
    exit 0
}

try {
    $json = $settings | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($settingsPath, $json, [System.Text.UTF8Encoding]::new($false))
} catch {
    Write-Host "[ERROR] Failed to write settings.json: $_" -ForegroundColor Red
    Write-Host "  Is the file open in another process? Close Claude Code and retry." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Removed $removed stale hook(s) from settings.json" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run full setup:  powershell -ExecutionPolicy Bypass -File `"$PSScriptRoot\setup.ps1`""
Write-Host "  2. Run /mcp in Claude Code"
