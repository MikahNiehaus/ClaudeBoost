# setup.ps1 - thin shim. The real setup is now scripts/setup.py (cross-platform).
#
# Kept so existing automation, docs, and ensure-setup copies on user machines
# that reference setup.ps1 keep working without modification.

$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
$setupPy = Join-Path $scriptDir "setup.py"

if (-not (Test-Path $setupPy)) {
    Write-Host "[ERROR] setup.py not found at $setupPy" -ForegroundColor Red
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

& $python.Source $setupPy
exit $LASTEXITCODE
