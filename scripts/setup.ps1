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
            env = @{
                RAG_PROJECT_ROOT = $boostHomePosix
            }
        }
    }
}

$mcpJson = $mcpConfig | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($mcpPath, $mcpJson, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] mcp.json - RAG server registered globally" -ForegroundColor Green

# --- 1b. Ensure ~/.claude.json also has rag-server with cwd ---
$claudeJsonPath = Join-Path $env:USERPROFILE ".claude.json"
if (Test-Path $claudeJsonPath) {
    $claudeJson = Get-Content $claudeJsonPath -Raw | ConvertFrom-Json
    if (-not $claudeJson.PSObject.Properties["mcpServers"]) {
        $claudeJson | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
    }
    $ragEntry = [PSCustomObject]@{
        type = "stdio"
        command = "python"
        args = @("-m", "rag_server")
        env = [PSCustomObject]@{ RAG_PROJECT_ROOT = $boostHome.Replace("\", "/") }
        cwd = $ragCwd
    }
    if ($claudeJson.mcpServers.PSObject.Properties["rag-server"]) {
        $claudeJson.mcpServers."rag-server" = $ragEntry
    } else {
        $claudeJson.mcpServers | Add-Member -NotePropertyName "rag-server" -NotePropertyValue $ragEntry
    }
    $claudeJsonOut = $claudeJson | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($claudeJsonPath, $claudeJsonOut, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] .claude.json - RAG server registered with cwd" -ForegroundColor Green
} else {
    Write-Host "[SKIP] .claude.json - not found (will use mcp.json)" -ForegroundColor Yellow
}

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

# --- 2a. Seed state directory (CONSULT mode + session approvals) ---
$stateDir = Join-Path $boostHome "state"
if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
    Write-Host "[OK] state/ directory created" -ForegroundColor Green
}
$modePath = Join-Path $stateDir "claudeboost-mode.json"
if (-not (Test-Path $modePath)) {
    $modeDefault = @{
        mode = "CONSULT"
        setAt = (Get-Date).ToString("o")
        setBy = "default"
        reason = "ClaudeBoost default"
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText($modePath, $modeDefault, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] state/claudeboost-mode.json - seeded CONSULT default" -ForegroundColor Green
} else {
    Write-Host "[SKIP] state/claudeboost-mode.json - preserving existing user setting" -ForegroundColor Yellow
}
$approvalsPath = Join-Path $stateDir "session-approvals.json"
if (-not (Test-Path $approvalsPath)) {
    [System.IO.File]::WriteAllText($approvalsPath, '{"sessionId":"","approvals":[]}', [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] state/session-approvals.json - seeded empty" -ForegroundColor Green
}

# Ensure hooks block exists
if (-not $settings.PSObject.Properties["hooks"]) {
    $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{})
}

# Helper: install a hook entry if its sentinel string isn't already present.
# - If the hook type doesn't exist, create it with the new entry.
# - If it exists and no prompt contains the sentinel, append the new entry.
# - If the sentinel is already present, skip (idempotent on upgrade).
function Install-HookEntry {
    param(
        [Parameter(Mandatory)] $Settings,
        [Parameter(Mandatory)] [string] $HookType,
        [Parameter(Mandatory)] $Entry,
        [Parameter(Mandatory)] [string] $Sentinel,
        [Parameter(Mandatory)] [string] $Label
    )
    if (-not $Settings.hooks.PSObject.Properties[$HookType]) {
        $Settings.hooks | Add-Member -NotePropertyName $HookType -NotePropertyValue @($Entry)
        Write-Host "[OK] hooks.$HookType - added $Label" -ForegroundColor Green
        return
    }
    $existing = @($Settings.hooks.$HookType)
    foreach ($e in $existing) {
        if ($e.hooks) {
            foreach ($h in $e.hooks) {
                if ($h.prompt -and $h.prompt.Contains($Sentinel)) {
                    Write-Host "[SKIP] hooks.$HookType - $Label already installed" -ForegroundColor Yellow
                    return
                }
            }
        }
    }
    $Settings.hooks.$HookType = @($existing) + @($Entry)
    Write-Host "[OK] hooks.$HookType - appended $Label" -ForegroundColor Green
}

# --- SessionStart: workflow routing (original) ---
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
Install-HookEntry -Settings $settings -HookType "SessionStart" -Entry $sessionHook `
    -Sentinel "Quality-first routing" -Label "workflow routing"

# --- SessionStart: CONSULT mode protocol (new) ---
$consultSessionHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "CLAUDEBOOST MODE — CONSULT vs AUTO:`n`nRead `$CLAUDEBOOST_HOME/state/claudeboost-mode.json at the start of each task. Field: ``mode``. Default CONSULT.`n`nIf mode=CONSULT, for any architectural decision you MUST:`n  1. rag_search(feature keywords) + read 2-3 project files. Cite file:line.`n  2. Spawn architect-agent (Opus) via Task with ``PROPOSAL_ONLY — citations: ...``.`n  3. Present 2-3 options via AskUserQuestion. User picks/edits/adds.`n  4. Log approval to `$CLAUDEBOOST_HOME/state/session-approvals.json.`n  5. Implement. RAG-required standards apply automatically.`n`nArchitectural = new endpoint, new class/module, new DB table, new dep, new middleware, auth/validation/error/logging strategy, new public API, new config surface, new concurrency model.`n`nNOT architectural = typo, 1-line fix, test, doc, value-only config tweak, rename in one file, edits under workspace/ .claude/ knowledge/ plans/ docs/.`n`nConsultation is ADDITIVE, not gatekeeping. Present what RAG requires as already-handled; invite the user to ADD constraints (size caps, character allowlists, rate limits). Do not debate whether to validate.`n`nCheck session-approvals.json before spawning architect-agent — if this axis was already decided, proceed with the approved choice.`n`nIf mode=AUTO: proceed autonomously, still cite sources."
            statusMessage = "Loading CONSULT mode protocol..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "SessionStart" -Entry $consultSessionHook `
    -Sentinel "CONSULT vs AUTO" -Label "CONSULT protocol"

# --- PreToolUse: agent spawn RAG enforcement (original) ---
$taskSpawnHook = [PSCustomObject]@{
    matcher = "Task"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "AGENT SPAWN — QUALITY ROUTING:`n1. ``rag_context`` as Step 1 (ALWAYS — agent name + task description)`n2. Workspace reference (if exists)`n3. ROUTE by agent type:`n   - Finding-producers (reviewer, security, performance): FULL spawn template with verify gate. Findings MUST cite file:line. Evaluator-agent WILL verify after.`n   - Research/support (explore, research, docs, estimator, teacher): LIGHTWEIGHT template — rag_context + task + status report. Skip verify gate.`n   - Implementation (workflow, refactor, debug, test, ui, database, devops, observability, architect, ticket-analyst, browser): STANDARD template. No verify gate unless auditing.`n4. GT context if available`nDo NOT proceed without rag_context."
            statusMessage = "Enforcing RAG context in agent spawn..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $taskSpawnHook `
    -Sentinel "AGENT SPAWN" -Label "Task RAG enforcement"

# --- PreToolUse: workspace creation (original) ---
$workspaceHook = [PSCustomObject]@{
    matcher = "Bash(mkdir*workspace*)"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "WORKSPACE CREATION CHECK: You are creating a workspace directory. Before proceeding:`n1. Call ``rag_search`` with the task description to find relevant knowledge`n2. If Gas Town is available, consider ``gt prime`` to initialize the workspace`n3. Ensure you have a task ID and will create context.md after this`nThis is the start of complex work - RAG and GT should be active."
            statusMessage = "Enforcing RAG lookup on workspace creation..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $workspaceHook `
    -Sentinel "WORKSPACE CREATION CHECK" -Label "workspace creation"

# --- PreToolUse: CONSULT gate on Edit/Write (new) ---
$consultEditHook = [PSCustomObject]@{
    matcher = "Edit|Write|MultiEdit"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "CONSULT GATE — quick check before this Edit/Write:`n`nIs this an architectural change? (new file others import, new dep, new endpoint, new table, new middleware, new validation/auth/error strategy, new config surface, new module)`n`n- NO → proceed.`n- YES → STOP. Read `$CLAUDEBOOST_HOME/state/claudeboost-mode.json. If mode=CONSULT and you have NOT yet: (a) called rag_search, (b) spawned architect-agent with PROPOSAL_ONLY + file:line citations, (c) logged user approval to state/session-approvals.json — do those now in order. No code yet. If mode=AUTO, proceed and cite the pattern you're following.`n`nCheck session-approvals.json first — if this axis was already approved this session, proceed with the approved choice.`n`nExempt: edits under workspace/, .claude/, knowledge/, plans/, docs/."
            statusMessage = "CONSULT gate check..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $consultEditHook `
    -Sentinel "CONSULT GATE" -Label "CONSULT gate on Edit/Write"

# --- PreToolUse: architect-agent PROPOSAL_ONLY contract (new) ---
$architectProposalHook = [PSCustomObject]@{
    matcher = "Task"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "architect-agent PROPOSAL_ONLY contract:`nIf spawning architect-agent in CONSULT mode for an architectural proposal, the spawn prompt MUST include:`n  1. The literal string ``PROPOSAL_ONLY``.`n  2. At least 2 file:line citations from the target project (format: ``path/file.ext:line-range — what it shows``).`narchitect-agent (Opus) will refuse and return BLOCKED if citations are missing. After architect-agent returns, the MAIN agent (not architect) presents options via AskUserQuestion and logs the user's approval to state/session-approvals.json before implementing."
            statusMessage = "Enforcing architect-agent proposal contract..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $architectProposalHook `
    -Sentinel "architect-agent PROPOSAL_ONLY contract" -Label "architect-agent proposal contract"

# --- PreToolUse: process-kill safety (persistent rule) ---
$killSafetyHook = [PSCustomObject]@{
    matcher = "Bash(pkill*)|Bash(killall*)|Bash(*Stop-Process*)|Bash(*taskkill*/IM*)"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "PROCESS KILL SAFETY — STOP and check:`n`nYou are about to run a process-killing command. Broad name-pattern kills (pkill NAME, killall NAME, Stop-Process -Name NAME, taskkill /IM NAME) can kill the user's unrelated processes. This has burned the user before.`n`nREQUIRED:`n- If you have a specific PID, use it: kill PID, Stop-Process -Id PID, taskkill /PID pid.`n- If targeting a container, use the explicit container name: docker stop NAME.`n- If you have only a name pattern and no PID, STOP and ask the user first. Never assume it is safe to broad-match.`n`nReason: prior incidents where broad kills hit unrelated processes. Specific PIDs or explicit container names only; never broad name patterns without explicit user approval."
            statusMessage = "Process kill safety check..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $killSafetyHook `
    -Sentinel "PROCESS KILL SAFETY" -Label "process kill safety"

# --- PostToolUse: verify gate (original) ---
$verifyGateHook = [PSCustomObject]@{
    matcher = "Task"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "VERIFY GATE: Scan agent output for BLOCKER/HIGH/MEDIUM findings.`n- If findings exist: spawn evaluator-agent to verify (fresh context prevents confirmation bias). Do NOT self-verify — same context that hallucinated will ``confirm`` the hallucination.`n- Evaluator checks: does each finding cite file:line? Does the code actually show the issue? Drop false positives.`n- No findings? No evaluator needed. Present results directly.`nRework from false findings costs more than one lightweight evaluator spawn."
            statusMessage = "Enforcing verify gate on agent output..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PostToolUse" -Entry $verifyGateHook `
    -Sentinel "VERIFY GATE: Scan agent output" -Label "verify gate"

# --- PreCompact: context preservation (original) ---
$preCompactHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "CONTEXT PRESERVATION — quality-first routing:`n1. Agent spawns: ``rag_context`` Step 1, route by type (full/standard/lightweight)`n2. Finding verification: ALWAYS evaluator-agent, never self-verify (confirmation bias)`n3. GT commands: ``gt prime``, ``gt sling``, ``gt handoff```n4. Decision flow: simple (just do it) vs complex (workspace + agents)`n5. Rework costs more than ceremony. Do it right the first time.`n6. CONSULT/AUTO mode file at `$CLAUDEBOOST_HOME/state/claudeboost-mode.json — re-check after compact. Default CONSULT: research + propose + ask before architectural decisions."
            statusMessage = "Preserving RAG/GT/CONSULT awareness before compaction..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreCompact" -Entry $preCompactHook `
    -Sentinel "CONTEXT PRESERVATION" -Label "context preservation"

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
