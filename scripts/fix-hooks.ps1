# fix-hooks.ps1 - thin shim. The real implementation is now scripts/fix_hooks.py
# (cross-platform). Kept so older RUN-ME-FIRST batch files and docs still work.

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$fixPy = Join-Path $scriptDir "fix_hooks.py"

if (-not (Test-Path $fixPy)) {
    Write-Host "[ERROR] fix_hooks.py not found at $fixPy" -ForegroundColor Red
    exit 1
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Host "[ERROR] Python not found on PATH. Install Python 3.9+." -ForegroundColor Red
    exit 1
}

& $python.Source $fixPy
exit $LASTEXITCODE
