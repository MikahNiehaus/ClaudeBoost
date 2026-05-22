# scripts/setup.ps1 - ClaudeBoost portable setup
# Run once after cloning: powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

$ErrorActionPreference = "Stop"

# Resolve ClaudeBoost install path from script location
$boostHome = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$boostHomePosix = $boostHome.Replace("\", "/")
$claudeDir = Join-Path $env:USERPROFILE ".claude"

Write-Host "`n=== ClaudeBoost Setup ===" -ForegroundColor Cyan
Write-Host "ClaudeBoost home: $boostHome"
Write-Host "Claude config dir: $claudeDir`n"

# --- 0. Preflight checks ---
Write-Host "Running preflight checks..." -ForegroundColor Cyan
$preflightOk = $true
foreach ($req in @(
    [PSCustomObject]@{ cmd = "python"; label = "Python 3.9+";     required = $true },
    [PSCustomObject]@{ cmd = "pip";    label = "pip";             required = $true },
    [PSCustomObject]@{ cmd = "claude"; label = "Claude Code CLI"; required = $true },
    [PSCustomObject]@{ cmd = "git";    label = "Git";             required = $false }
)) {
    if (Get-Command $req.cmd -ErrorAction SilentlyContinue) {
        Write-Host "[OK] $($req.label)" -ForegroundColor Green
    } elseif ($req.required) {
        Write-Host "[ERROR] $($req.label) not found on PATH — install before re-running /setup." -ForegroundColor Red
        $preflightOk = $false
    } else {
        Write-Host "[WARN] $($req.label) not found — gt commands and workspace commits will not work." -ForegroundColor Yellow
    }
}
if (-not $preflightOk) {
    Write-Host "`n[FAIL] Required tools missing. Fix the above and re-run /setup." -ForegroundColor Red
    exit 1
}

# Ensure ~/.claude exists
if (-not (Test-Path $claudeDir)) {
    New-Item -ItemType Directory -Path $claudeDir | Out-Null
    Write-Host "Created $claudeDir" -ForegroundColor Yellow
}

# --- 1. Create/update ~/.claude/mcp.json (merge — never overwrite other servers) ---
$mcpPath = Join-Path $claudeDir "mcp.json"
$ragCwd = (Join-Path $boostHome "mcp-rag-server").Replace("\", "/")

$ragEntry = [PSCustomObject]@{
    command = "python"
    args    = @("-m", "rag_server")
    cwd     = $ragCwd
    env     = [PSCustomObject]@{ RAG_PROJECT_ROOT = $boostHomePosix }
}

if (Test-Path $mcpPath) {
    # Merge: read existing, upsert rag-server, preserve all other servers
    $existingMcp = Get-Content $mcpPath -Raw | ConvertFrom-Json
    if (-not $existingMcp.PSObject.Properties["mcpServers"]) {
        $existingMcp | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
    }
    if ($existingMcp.mcpServers.PSObject.Properties["rag-server"]) {
        $existingMcp.mcpServers."rag-server" = $ragEntry
    } else {
        $existingMcp.mcpServers | Add-Member -NotePropertyName "rag-server" -NotePropertyValue $ragEntry
    }
    $mcpJson = $existingMcp | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText($mcpPath, $mcpJson, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] mcp.json - rag-server merged (existing MCP servers preserved)" -ForegroundColor Green
} else {
    $mcpConfig = [PSCustomObject]@{ mcpServers = [PSCustomObject]@{ "rag-server" = $ragEntry } }
    $mcpJson = $mcpConfig | ConvertTo-Json -Depth 6
    [System.IO.File]::WriteAllText($mcpPath, $mcpJson, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] mcp.json - created with rag-server" -ForegroundColor Green
}

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
    try {
        $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
    } catch {
        Write-Host "[ERROR] settings.json is malformed JSON — validate or delete it and re-run /setup." -ForegroundColor Red
        Write-Host "  Path: $settingsPath" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[WARN] settings.json not found - creating minimal config" -ForegroundColor Yellow
    $settings = [PSCustomObject]@{}
}

# Ensure env block exists and add CLAUDEBOOST_HOME
if (-not $settings.PSObject.Properties["env"]) {
    $settings | Add-Member -NotePropertyName "env" -NotePropertyValue ([PSCustomObject]@{})
}
if ($settings.env.PSObject.Properties["CLAUDEBOOST_HOME"]) {
    $settings.env.CLAUDEBOOST_HOME = $boostHomePosix
} else {
    $settings.env | Add-Member -NotePropertyName "CLAUDEBOOST_HOME" -NotePropertyValue $boostHomePosix
}

# Configure statusLine — create if missing, fix path if stale
$statusLineCmdTemplate = "printf '\033[32;1m> ClaudeBoost\033[0m'; [ -f ""`$TEMP/claudeboost_rag_ok"" ] && printf ' \033[2m|\033[0m \033[32;1mBoost RAG\033[0m'; [ -f ""`$TEMP/claudeboost_project_rag_ok"" ] && printf ' \033[2m|\033[0m \033[36;1mProject RAG\033[0m'; command -v gt >/dev/null 2>&1 && printf ' \033[2m|\033[0m \033[33;1mGT\033[0m'"
if ($settings.PSObject.Properties["statusLine"]) {
    $cmd = $settings.statusLine.command
    if ($cmd -and $cmd.Contains('$LOCALAPPDATA/Temp')) {
        $settings.statusLine.command = $cmd.Replace('$LOCALAPPDATA/Temp', '$TEMP')
        Write-Host "[OK] statusLine - fixed to use `$TEMP" -ForegroundColor Green
    } else {
        Write-Host "[SKIP] statusLine - already configured" -ForegroundColor Yellow
    }
} else {
    $settings | Add-Member -NotePropertyName "statusLine" -NotePropertyValue ([PSCustomObject]@{
        type = "command"
        command = $statusLineCmdTemplate
    })
    Write-Host "[OK] statusLine - created ClaudeBoost status bar" -ForegroundColor Green
}

# --- 2b. Sync slash commands to global ~/.claude/commands (repo is source of truth) ---
# Project .claude/commands only load when cwd is inside the ClaudeBoost repo.
# Mirroring them to the global dir makes every command available in every Claude instance.
$cmdSrc = Join-Path $boostHome ".claude\commands"
$cmdDst = Join-Path $claudeDir "commands"
if (Test-Path $cmdSrc) {
    if (-not (Test-Path $cmdDst)) {
        New-Item -ItemType Directory -Path $cmdDst | Out-Null
    }
    $cmdNew = 0; $cmdUpd = 0; $cmdSame = 0
    foreach ($srcFile in Get-ChildItem -Path $cmdSrc -Filter *.md -File) {
        $dstFile = Join-Path $cmdDst $srcFile.Name
        if (-not (Test-Path $dstFile)) {
            Copy-Item $srcFile.FullName $dstFile -Force
            $cmdNew++
        } elseif ((Get-FileHash $srcFile.FullName).Hash -ne (Get-FileHash $dstFile).Hash) {
            Copy-Item $srcFile.FullName $dstFile -Force
            $cmdUpd++
        } else {
            $cmdSame++
        }
    }
    Write-Host "[OK] slash commands synced to global - $cmdNew new, $cmdUpd updated, $cmdSame unchanged" -ForegroundColor Green
} else {
    Write-Host "[SKIP] slash commands - source dir not found: $cmdSrc" -ForegroundColor Yellow
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
        setBy = "setup"
        reason = "ClaudeBoost default"
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText($modePath, $modeDefault, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] state/claudeboost-mode.json - seeded CONSULT default" -ForegroundColor Green
} else {
    # File exists — check if mode is CONSULT. If not, reset to CONSULT (setup always enforces the default).
    try {
        $existingMode = (Get-Content $modePath -Raw | ConvertFrom-Json).mode
    } catch {
        $existingMode = "UNKNOWN"
    }
    if ($existingMode -eq "CONSULT") {
        Write-Host "[OK] state/claudeboost-mode.json - already CONSULT" -ForegroundColor Green
    } else {
        $modeReset = @{
            mode = "CONSULT"
            setAt = (Get-Date).ToString("o")
            setBy = "setup"
            reason = "reset to default by /setup (was: $existingMode)"
        } | ConvertTo-Json
        [System.IO.File]::WriteAllText($modePath, $modeReset, [System.Text.UTF8Encoding]::new($false))
        Write-Host "[OK] state/claudeboost-mode.json - reset to CONSULT (was: $existingMode)" -ForegroundColor Green
    }
}
$approvalsPath = Join-Path $stateDir "session-approvals.json"
if (-not (Test-Path $approvalsPath)) {
    [System.IO.File]::WriteAllText($approvalsPath, '{"sessionId":"","approvals":[]}', [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] state/session-approvals.json - seeded empty" -ForegroundColor Green
} else {
    Write-Host "[SKIP] state/session-approvals.json - preserving existing session data" -ForegroundColor Yellow
}
$speakPath = Join-Path $stateDir "speak-state.json"
if (-not (Test-Path $speakPath)) {
    $speakDefault = @{
        enabled = $false
        voice = "en-US-AndrewNeural"
        setAt = (Get-Date).ToString("o")
        setBy = "default"
    } | ConvertTo-Json
    [System.IO.File]::WriteAllText($speakPath, $speakDefault, [System.Text.UTF8Encoding]::new($false))
    Write-Host "[OK] state/speak-state.json - seeded TTS disabled default" -ForegroundColor Green
} else {
    Write-Host "[SKIP] state/speak-state.json - preserving existing setting" -ForegroundColor Yellow
}

# Ensure hooks block exists
if (-not $settings.PSObject.Properties["hooks"]) {
    $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue ([PSCustomObject]@{})
}

# Helper: install a hook entry if its sentinel string isn't already present.
# - If the hook type doesn't exist, create it with the new entry.
# - If it exists and neither prompt nor command contains the sentinel, append the new entry.
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
                if (($h.prompt -and $h.prompt.Contains($Sentinel)) -or ($h.command -and $h.command.Contains($Sentinel))) {
                    # Sentinel found — update matcher if it has changed (e.g. adding Bash to an existing entry)
                    if ($e.PSObject.Properties["matcher"] -and $Entry.PSObject.Properties["matcher"] -and $e.matcher -ne $Entry.matcher) {
                        $e.matcher = $Entry.matcher
                        Write-Host "[OK] hooks.$HookType - updated matcher for $Label ($($Entry.matcher))" -ForegroundColor Green
                    } else {
                        Write-Host "[SKIP] hooks.$HookType - $Label already installed" -ForegroundColor Yellow
                    }
                    return
                }
            }
        }
    }
    $Settings.hooks.$HookType = @($existing) + @($Entry)
    Write-Host "[OK] hooks.$HookType - appended $Label" -ForegroundColor Green
}

# Helper: detect stale hook commands.
# Stale = (1) contains literal $CLAUDEBOOST_HOME bash variable, or
#         (2) references an absolute python script path that no longer exists on disk.
function Test-HookCommandStale {
    param([string] $Command)
    if ($Command -like '*$CLAUDEBOOST_HOME*') { return $true }
    $m = [regex]::Match($Command, 'python\s+"([^"]+\.py)"')
    if ($m.Success) {
        $scriptPath = $m.Groups[1].Value -replace '/', '\'
        if (-not (Test-Path $scriptPath)) { return $true }
    }
    return $false
}

# Helper: remove stale individual hooks from all entries.
# Filters at the individual hook level — healthy sibling hooks in the same entry are preserved.
# Removes the entry key entirely only if ALL hooks within it were stale.
function Remove-StaleVariableHooks {
    param($Settings)
    $removed = 0
    foreach ($hookType in @($Settings.hooks.PSObject.Properties.Name)) {
        if ([string]::IsNullOrEmpty($hookType)) { continue }
        $entries    = @($Settings.hooks.$hookType)
        $newEntries = @()
        foreach ($entry in $entries) {
            if ($entry.hooks) {
                $healthyHooks = @()
                foreach ($h in @($entry.hooks)) {
                    if ($h.command -and (Test-HookCommandStale ([string]$h.command))) {
                        $preview = ([string]$h.command).Substring(0, [Math]::Min(70, ([string]$h.command).Length))
                        Write-Host "[CLEAN] hooks.$hookType - removing stale hook: $preview..." -ForegroundColor Yellow
                        $removed++
                    } else {
                        $healthyHooks += $h
                    }
                }
                if ($healthyHooks.Count -gt 0) {
                    $entry.hooks = $healthyHooks
                    $newEntries += $entry
                }
                # Entry entirely dropped only if all its hooks were stale
            } else {
                $newEntries += $entry
            }
        }
        if ($newEntries.Count -gt 0) {
            $Settings.hooks.$hookType = $newEntries
        } else {
            $Settings.hooks.PSObject.Properties.Remove($hookType)
        }
    }
    if ($removed -gt 0) {
        Write-Host "[OK] Removed $removed stale hook(s)" -ForegroundColor Green
    } else {
        Write-Host "[OK] No stale hooks found" -ForegroundColor Green
    }
}

Write-Host "`nCleaning up stale hooks..." -ForegroundColor Cyan
Remove-StaleVariableHooks -Settings $settings

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

# --- SessionStart: codebase RAG (project_path reminder) ---
$codebaseRagHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "CODEBASE RAG: When calling rag_context or instructing agents to call rag_context, always include project_path set to the primary working directory. This enables Tier 4 codebase search so agents automatically get relevant source code from the target project. When using rag_search for code understanding, use scope='codebase' with the project_path. If the project has not been indexed yet, suggest /index-project first."
            statusMessage = "Loading codebase RAG..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "SessionStart" -Entry $codebaseRagHook `
    -Sentinel "CODEBASE RAG" -Label "codebase RAG reminder"

# --- SessionStart: compaction restore (injects memo after compaction) ---
$compactionRestorePath = "$boostHome\scripts\compaction-restore.py".Replace("\", "/")
$compactionRestoreHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$compactionRestorePath`""
            timeout = 5000
            statusMessage = "Restoring context after compaction..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "SessionStart" -Entry $compactionRestoreHook `
    -Sentinel "compaction-restore.py" -Label "compaction restore (command-type)"

# --- PreToolUse: agent-spawn gate on Task (command-type) ---
# Command-type hook (not prompt). The old prompt-type hook instructed the
# judging LLM to "evaluate" whether rag_context was called, but prompt hooks
# have no tool access so the LLM just had to guess, and the em-dashes in the
# hook text got re-encoded to mojibake across setup runs (sentinel didn't
# match, duplicates piled up). agent-spawn-gate.py reads the Task tool_input
# directly and emits a non-blocking stderr nudge if rag_context or the
# architect-agent PROPOSAL_ONLY contract is missing. Never blocks.
$agentGatePath = "$boostHome\scripts\agent-spawn-gate.py".Replace("\", "/")
$taskSpawnHook = [PSCustomObject]@{
    matcher = "Task"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$agentGatePath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $taskSpawnHook `
    -Sentinel "agent-spawn-gate.py" -Label "Task RAG/proposal gate (command-type)"

# --- PreToolUse: workspace boost gate (blocks mkdir workspace/* if /boost not run) ---
# Hard block (exit 2): if /boost sentinel is absent, workspace creation is denied.
# RAG must be verified before a workspace is created — otherwise rag_context won't
# load correctly into the workspace and the whole session starts on a broken footing.
$workspaceBoostGatePath = "$boostHome\scripts\workspace-boost-gate.py".Replace("\", "/")
$workspaceBoostGateHook = [PSCustomObject]@{
    matcher = "Bash(mkdir*workspace*)"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$workspaceBoostGatePath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $workspaceBoostGateHook `
    -Sentinel "workspace-boost-gate.py" -Label "workspace boost gate (command-type)"

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

# --- PreToolUse: CONSULT gate on Edit/Write ---
# Command-type hook (not prompt). Prompt-type hooks are pure LLM judgment and
# cannot read files, so they can't actually check mode.json or session-approvals
# even though prior prompt text told the LLM to. This over-fired and blocked
# legitimate edits. consult-gate.py reads both state files and decides:
#   AUTO              -> exit 0, silent
#   CONSULT + exempt  -> exit 0, silent
#   CONSULT + other   -> exit 0, stderr nudge (non-blocking reminder)
$consultGatePath = "$boostHome\scripts\consult-gate.py".Replace("\", "/")
$consultEditHook = [PSCustomObject]@{
    matcher = "Edit|Write|MultiEdit|Bash"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$consultGatePath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $consultEditHook `
    -Sentinel "consult-gate.py" -Label "CONSULT gate on Edit/Write/Bash (command-type)"

# --- architect-agent PROPOSAL_ONLY contract is handled by agent-spawn-gate.py
# above (command-type hook). No separate prompt-type hook needed; the old one
# over-fired the same way as the AGENT SPAWN hook and is no longer installed.

# --- PreToolUse: Bash guard (blocks commands that trigger permission prompts) ---
# Command-type hook (BLOCKING — exit 2). Catches two patterns:
#   1. cd "/path" && command — triggers "bare repository attack" prompt
#   2. Backslash-escaped spaces — triggers "backslash-escaped whitespace" prompt
# Claude sees the block message and retries with the correct pattern.
$bashGuardPath = "$boostHome\scripts\bash-guard.py".Replace("\", "/")
$bashGuardHook = [PSCustomObject]@{
    matcher = "Bash"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$bashGuardPath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreToolUse" -Entry $bashGuardHook `
    -Sentinel "bash-guard.py" -Label "Bash guard (command-type)"

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

# --- PostToolUse: context nudge (counter-based, all tools) ---
$contextNudgePath = "$boostHome\scripts\context-nudge.py".Replace("\", "/")
$contextNudgeHook = [PSCustomObject]@{
    matcher = ".*"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$contextNudgePath`""
            timeout = 3000
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PostToolUse" -Entry $contextNudgeHook `
    -Sentinel "context-nudge.py" -Label "context nudge (command-type)"

# --- PostToolUse: project RAG flag (rag_index_project success indicator) ---
$projectRagFlagPath = "$boostHome\scripts\project-rag-flag.py".Replace("\", "/")
$projectRagFlagHook = [PSCustomObject]@{
    matcher = "mcp__rag-server__rag_index_project"
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$projectRagFlagPath`""
            timeout = 3000
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PostToolUse" -Entry $projectRagFlagHook `
    -Sentinel "project-rag-flag.py" -Label "project RAG flag (command-type)"

# --- PreCompact: context preservation + compaction save ---
$compactionSavePath = "$boostHome\scripts\compaction-save.py".Replace("\", "/")
$preCompactHook = [PSCustomObject]@{
    matcher = "Always"
    hooks = @(
        [PSCustomObject]@{
            type = "prompt"
            prompt = "CONTEXT PRESERVATION — quality-first routing:`n1. Agent spawns: ``rag_context`` Step 1, route by type (full/standard/lightweight)`n2. Finding verification: ALWAYS evaluator-agent, never self-verify (confirmation bias)`n3. GT commands: ``gt prime``, ``gt sling``, ``gt handoff```n4. Decision flow: simple (just do it) vs complex (workspace + agents)`n5. Rework costs more than ceremony. Do it right the first time.`n6. CONSULT/AUTO mode file at `$CLAUDEBOOST_HOME/state/claudeboost-mode.json — re-check after compact. Default CONSULT: research + propose + ask before architectural decisions."
            statusMessage = "Preserving RAG/GT/CONSULT awareness before compaction..."
        }
        [PSCustomObject]@{
            type = "command"
            command = "python `"$compactionSavePath`""
            timeout = 5000
            statusMessage = "Saving working state before compaction..."
        }
    )
}
Install-HookEntry -Settings $settings -HookType "PreCompact" -Entry $preCompactHook `
    -Sentinel "CONTEXT PRESERVATION" -Label "context preservation + compaction save"

# --- SessionEnd: clear handoff save ---
# Saves workspace context + transcript highlights to state/handoff-latest.json
# whenever the user runs /clear (source=clear) or the session ends naturally.
# This must be in GLOBAL settings so it fires in every project, not just ClaudeBoost.
$clearSavePath = "$boostHome\scripts\session-clear-save.py".Replace("\", "/")
$clearSaveHook = [PSCustomObject]@{
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$clearSavePath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "SessionEnd" -Entry $clearSaveHook `
    -Sentinel "session-clear-save.py" -Label "clear handoff save"

# --- UserPromptSubmit: ensure-setup bootstrap (must be first — no CLAUDEBOOST_HOME dependency) ---
# Copied to ~/.claude/ensure-setup.py so the hook path is stable across machines:
# $HOME always resolves to the correct user directory regardless of username or OS path.
# Self-locating via __file__; fires silently when setup is already done.
$ensureSetupSrc  = Join-Path $boostHome "scripts\ensure-setup.py"
$ensureSetupDest = Join-Path $claudeDir "ensure-setup.py"
Copy-Item -Path $ensureSetupSrc -Destination $ensureSetupDest -Force
Write-Host "[OK] ensure-setup.py copied to $ensureSetupDest" -ForegroundColor Green

$ensureSetupHook = [PSCustomObject]@{
    hooks = @(
        [PSCustomObject]@{
            type    = "command"
            command = 'python "$HOME/.claude/ensure-setup.py"'
            timeout = 10000
        }
    )
}
Install-HookEntry -Settings $settings -HookType "UserPromptSubmit" -Entry $ensureSetupHook `
    -Sentinel "ensure-setup.py" -Label "auto-setup bootstrap"

# --- UserPromptSubmit: TTS interrupt (stop playback on user input) ---
$speakStopPath = "$boostHome\scripts\speak-stop.py".Replace("\", "/")
$speakStopHook = [PSCustomObject]@{
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$speakStopPath`""
            timeout = 3000
        }
    )
}
Install-HookEntry -Settings $settings -HookType "UserPromptSubmit" -Entry $speakStopHook `
    -Sentinel "speak-stop.py" -Label "TTS interrupt (command-type)"

# --- Stop: human voice guard (command-type) ---
$humanVoiceGuardPath = "$boostHome\scripts\human-voice-guard.py".Replace("\", "/")
$humanVoiceGuardHook = [PSCustomObject]@{
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$humanVoiceGuardPath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "Stop" -Entry $humanVoiceGuardHook `
    -Sentinel "human-voice-guard.py" -Label "human voice guard"

# --- Stop: TTS speak hook (command-type) ---
$speakHookPath = "$boostHome\scripts\speak-tts.py".Replace("\", "/")
$speakHook = [PSCustomObject]@{
    hooks = @(
        [PSCustomObject]@{
            type = "command"
            command = "python `"$speakHookPath`""
        }
    )
}
Install-HookEntry -Settings $settings -HookType "Stop" -Entry $speakHook `
    -Sentinel "speak-tts.py" -Label "TTS speak hook"

$settingsJson = $settings | ConvertTo-Json -Depth 10
# BOM prevention: WriteAllText with UTF8Encoding.new($false) writes UTF-8 without BOM.
# (Set-Content -Encoding UTF8 in PowerShell 5.1 adds a BOM that breaks Claude Code JSON parsing.)
[System.IO.File]::WriteAllText($settingsPath, $settingsJson, [System.Text.UTF8Encoding]::new($false))
Write-Host "[OK] settings.json - CLAUDEBOOST_HOME env added" -ForegroundColor Green

# Helper: run a native command (pip/python/etc) and return stdout+stderr text
# without letting stderr flip $ErrorActionPreference="Stop" into a thrown
# exception. Native stderr captured via 2>&1 surfaces as ErrorRecord objects,
# which "Stop" mode turns into terminating errors — that swallowed real pip
# success as a generic RemoteException in earlier setup runs. Trust the exit
# code instead.
function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)] [string] $File,
        [Parameter(Mandatory)] [string[]] $Arguments
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $merged = & $File @Arguments 2>&1 | ForEach-Object { "$_" }
        return [PSCustomObject]@{
            ExitCode = $LASTEXITCODE
            Output   = ($merged -join "`n")
        }
    } finally {
        $ErrorActionPreference = $prev
    }
}

# --- 3. Verify RAG server ---
Write-Host "`nVerifying RAG server..." -ForegroundColor Cyan
$ragDir = Join-Path $boostHome "mcp-rag-server"

# Always install from ClaudeBoost (editable mode) to ensure correct source path.
Write-Host "Installing RAG server from $ragDir (editable mode)..." -ForegroundColor Cyan
$pipResult = Invoke-NativeCommand -File "pip" -Arguments @("install", "-e", $ragDir)
if ($pipResult.ExitCode -ne 0) {
    Write-Host "[WARN] pip install returned exit code $($pipResult.ExitCode)" -ForegroundColor Yellow
    Write-Host $pipResult.Output -ForegroundColor Yellow
    Write-Host "  Run manually: pip install -e $ragDir" -ForegroundColor Yellow
} else {
    Write-Host "[OK] RAG server installed (editable mode)" -ForegroundColor Green
}

# Eagerly upgrade the ML stack so transformers/tokenizers stay in sync.
# Another project installing a newer tokenizers can leave an older
# transformers in an incompatible state, producing ImportError at startup.
Write-Host "Upgrading ML deps (sentence-transformers + transformers + tokenizers)..." -ForegroundColor Cyan
$mlResult = Invoke-NativeCommand -File "pip" -Arguments @("install", "--upgrade", "--upgrade-strategy", "eager", "sentence-transformers", "transformers", "tokenizers")
if ($mlResult.ExitCode -ne 0) {
    Write-Host "[WARN] ML-deps upgrade returned exit code $($mlResult.ExitCode)" -ForegroundColor Yellow
    Write-Host $mlResult.Output -ForegroundColor Yellow
} else {
    Write-Host "[OK] ML deps upgraded" -ForegroundColor Green
}

# Remove torchvision if it's incompatible with the installed torch.
# We only do text embeddings so torchvision is never needed. A CUDA-built
# torchvision installed alongside CPU torch raises RuntimeError on import,
# breaking the entire sentence_transformers import chain.
$tvCheck = Invoke-NativeCommand -File "python" -Arguments @("-c", "import torchvision")
if ($tvCheck.ExitCode -ne 0) {
    Write-Host "torchvision import failed — uninstalling incompatible build..." -ForegroundColor Yellow
    $tvUninstall = Invoke-NativeCommand -File "pip" -Arguments @("uninstall", "torchvision", "-y")
    if ($tvUninstall.ExitCode -eq 0) {
        Write-Host "[OK] torchvision removed" -ForegroundColor Green
    } else {
        Write-Host "[WARN] Could not remove torchvision: $($tvUninstall.Output)" -ForegroundColor Yellow
    }
}

# Full health check — catches version drift a path-only check would miss.
$healthScript = Join-Path $boostHome "scripts\check-rag-health.py"
$healthResult = Invoke-NativeCommand -File "python" -Arguments @($healthScript)
if ($healthResult.ExitCode -eq 0) {
    Write-Host "[OK] RAG server healthy: $($healthResult.Output)" -ForegroundColor Green
} else {
    Write-Host "[WARN] RAG server health check failed (exit $($healthResult.ExitCode))" -ForegroundColor Yellow
    Write-Host $healthResult.Output -ForegroundColor Yellow
    Write-Host "  Run manually: python scripts\reinstall-rag.py" -ForegroundColor Yellow
}

# --- 3b. Ensure edge-tts is installed (for /speak TTS) ---
Write-Host "`nVerifying edge-tts..." -ForegroundColor Cyan
$edgeCheck = Invoke-NativeCommand -File "python" -Arguments @("-c", "import edge_tts; print('ok')")
if ($edgeCheck.ExitCode -eq 0 -and $edgeCheck.Output.Trim() -eq "ok") {
    Write-Host "[OK] edge-tts already installed" -ForegroundColor Green
} else {
    Write-Host "Installing edge-tts..." -ForegroundColor Yellow
    $edgeInstall = Invoke-NativeCommand -File "pip" -Arguments @("install", "edge-tts")
    if ($edgeInstall.ExitCode -eq 0) {
        Write-Host "[OK] edge-tts installed" -ForegroundColor Green
    } else {
        Write-Host "[WARN] edge-tts install failed - /speak will not work until you run: pip install edge-tts" -ForegroundColor Yellow
        Write-Host $edgeInstall.Output -ForegroundColor Yellow
    }
}

# --- Summary ---
Write-Host "`n=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "  CLAUDEBOOST_HOME = $boostHomePosix"
Write-Host "  RAG server registered in $mcpPath"
Write-Host "  Hooks configured (SessionStart, SessionEnd, PreToolUse, PostToolUse, PreCompact, UserPromptSubmit, Stop)"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run /mcp in Claude Code to reconnect"
Write-Host "  2. Run /boost to verify all systems"
Write-Host "  3. Run /speak on to enable text-to-speech"
Write-Host "  4. (Optional) Rebuild Gas Town with 'make build' if gt errors occur"
Write-Host ""
Write-Host "Troubleshooting:" -ForegroundColor Yellow
Write-Host "  If Claude Code is completely blocked (UserPromptSubmit hook error):"
Write-Host "  Run fix-hooks.ps1 first, then re-run setup.ps1:"
Write-Host "    powershell -ExecutionPolicy Bypass -File `"$boostHome\scripts\fix-hooks.ps1`""
Write-Host ""
