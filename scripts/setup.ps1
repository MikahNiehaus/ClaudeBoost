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
[System.IO.File]::WriteAllText($mcpPath, $mcpJson, [System.Text.UTF8Encoding]::new($false))
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

# Ensure hooks block exists
if (-not $settings.PSObject.Properties["hooks"]) {
    $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{})
}

# Add SessionStart hook if not present
$sessionHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "Quality-first routing: Check CLAUDE.md decision flow. For each action, pick the RIGHT approach — not the cheapest, not the most ceremonial. Full ceremony where quality demands it (reviews, security, architecture). Lightweight where it doesn't (explore, research, docs). Always use evaluator-agent for finding verification — never self-verify findings (confirmation bias). Rework costs more than doing it right."
            statusMessage = "Loading ClaudeBoost workflow..."
            timeout = 15
        }
    )
}
if (-not $settings.hooks.PSObject.Properties["SessionStart"]) {
    $settings.hooks | Add-Member -NotePropertyName "SessionStart" -NotePropertyValue @($sessionHook)
    Write-Host "[OK] hooks.SessionStart - added workflow hook" -ForegroundColor Green
} else {
    Write-Host "[SKIP] hooks.SessionStart - already exists" -ForegroundColor Yellow
}

# Add PreToolUse hooks (agent spawn + workspace creation enforcement)
$preToolUseHooks = @(
    [PSCustomObject]@{
        matcher = "Task"
        hooks = @(
            [PSCustomObject]@{
                type = "prompt"
                prompt = "AGENT SPAWN — QUALITY ROUTING:`n1. ``rag_context`` as Step 1 (ALWAYS — agent name + task description)`n2. Workspace reference (if exists)`n3. ROUTE by agent type:`n   - Finding-producers (reviewer, security, performance): FULL spawn template with verify gate. Findings MUST cite file:line. Evaluator-agent WILL verify after.`n   - Research/support (explore, research, docs, estimator, teacher): LIGHTWEIGHT template — rag_context + task + status report. Skip verify gate.`n   - Implementation (workflow, refactor, debug, test, ui, database, devops, observability, architect, ticket-analyst, browser): STANDARD template. No verify gate unless auditing.`n4. GT context if available`nDo NOT proceed without rag_context."
                statusMessage = "Enforcing RAG context in agent spawn..."
            }
        )
    },
    [PSCustomObject]@{
        matcher = "Bash(mkdir*workspace*)"
        hooks = @(
            [PSCustomObject]@{
                type = "prompt"
                prompt = "WORKSPACE CREATION CHECK: You are creating a workspace directory. Before proceeding:`n1. Call ``rag_search`` with the task description to find relevant knowledge`n2. If Gas Town is available, consider ``gt prime`` to initialize the workspace`n3. Ensure you have a task ID and will create context.md after this`nThis is the start of complex work - RAG and GT should be active."
                statusMessage = "Enforcing RAG lookup on workspace creation..."
            }
        )
    }
)
if (-not $settings.hooks.PSObject.Properties["PreToolUse"]) {
    $settings.hooks | Add-Member -NotePropertyName "PreToolUse" -NotePropertyValue $preToolUseHooks
    Write-Host "[OK] hooks.PreToolUse - added agent spawn + workspace enforcement" -ForegroundColor Green
} else {
    Write-Host "[SKIP] hooks.PreToolUse - already exists (review manually if needed)" -ForegroundColor Yellow
}

# Add PostToolUse hook (verify gate enforcement on agent output)
$postToolUseHooks = @(
    [PSCustomObject]@{
        matcher = "Task"
        hooks = @(
            [PSCustomObject]@{
                type = "prompt"
                prompt = "VERIFY GATE: Scan agent output for BLOCKER/HIGH/MEDIUM findings.`n- If findings exist: spawn evaluator-agent to verify (fresh context prevents confirmation bias). Do NOT self-verify — same context that hallucinated will ``confirm`` the hallucination.`n- Evaluator checks: does each finding cite file:line? Does the code actually show the issue? Drop false positives.`n- No findings? No evaluator needed. Present results directly.`nRework from false findings costs more than one lightweight evaluator spawn."
                statusMessage = "Enforcing verify gate on agent output..."
            }
        )
    }
)
if (-not $settings.hooks.PSObject.Properties["PostToolUse"]) {
    $settings.hooks | Add-Member -NotePropertyName "PostToolUse" -NotePropertyValue $postToolUseHooks
    Write-Host "[OK] hooks.PostToolUse - added verify gate enforcement" -ForegroundColor Green
} else {
    Write-Host "[SKIP] hooks.PostToolUse - already exists" -ForegroundColor Yellow
}

# Add PreCompact hook (context preservation)
$preCompactHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "CONTEXT PRESERVATION — quality-first routing:`n1. Agent spawns: ``rag_context`` Step 1, route by type (full/standard/lightweight)`n2. Finding verification: ALWAYS evaluator-agent, never self-verify (confirmation bias)`n3. GT commands: ``gt prime``, ``gt sling``, ``gt handoff```n4. Decision flow: simple (just do it) vs complex (workspace + agents)`n5. Rework costs more than ceremony. Do it right the first time."
            statusMessage = "Preserving RAG/GT awareness before compaction..."
        }
    )
}
if (-not $settings.hooks.PSObject.Properties["PreCompact"]) {
    $settings.hooks | Add-Member -NotePropertyName "PreCompact" -NotePropertyValue @($preCompactHook)
    Write-Host "[OK] hooks.PreCompact - added context preservation hook" -ForegroundColor Green
} else {
    Write-Host "[SKIP] hooks.PreCompact - already exists" -ForegroundColor Yellow
}

$settingsJson = $settings | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($settingsPath, $settingsJson, [System.Text.UTF8Encoding]::new($false))
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
Write-Host "  Hooks configured (SessionStart, PreToolUse, PostToolUse, PreCompact)"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Restart Claude Code for MCP changes to take effect"
Write-Host "  2. Run /boost to verify all systems"
Write-Host "  3. (Optional) Rebuild Gas Town with 'make build' if gt errors occur"
Write-Host ""
