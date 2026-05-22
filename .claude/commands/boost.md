---
description: Activate ClaudeBoost - always load RAG + GT and prime the session
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Banner and Clear Caches

Print the header, then clear Python bytecode caches and old sentinel files:
```bash
python "$CLAUDEBOOST_HOME/scripts/boost-inline.py" && rm -f "$TEMP/claudeboost_rag_ok" && rm -f "$TEMP/claudeboost_project_rag_ok" && find "$CLAUDEBOOST_HOME/mcp-rag-server" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; echo "  caches cleared"
```

## Step 1: Verify Privacy (auto-fix)

```bash
FIXED="" && if [ -z "$DISABLE_TELEMETRY" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_TELEMETRY', '1', 'User')"; export DISABLE_TELEMETRY=1; FIXED="$FIXED DISABLE_TELEMETRY"; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then powershell -Command "[System.Environment]::SetEnvironmentVariable('DISABLE_ERROR_REPORTING', '1', 'User')"; export DISABLE_ERROR_REPORTING=1; FIXED="$FIXED DISABLE_ERROR_REPORTING"; fi && if [ -n "$FIXED" ]; then echo "  auto-fixed:$FIXED"; fi && echo "  privacy: ok"
```

If any vars were auto-fixed, mention it briefly.

## Step 2: Activate RAG (MANDATORY — verify, auto-fix, and load)

Run the full health check. Exit code 2 or 3 triggers auto-repair:
```bash
python "$CLAUDEBOOST_HOME/scripts/check-rag-health.py"; RC=$?; if [ $RC -eq 0 ]; then echo "  RAG: healthy"; elif [ $RC -eq 2 ] || [ $RC -eq 3 ]; then echo "  RAG: needs repair (exit $RC) — running reinstall..."; python "$CLAUDEBOOST_HOME/scripts/reinstall-rag.py" && python "$CLAUDEBOOST_HOME/scripts/check-rag-health.py" && echo "  RAG: repaired" || echo "  RAG: repair failed — run setup.ps1"; else echo "  RAG: unknown failure (exit $RC) — run setup.ps1"; fi
```

Call `rag_status` (MCP tool) to verify the server is running and has indexed content.

Then **actively load RAG context** — this primes the session:
```
rag_context(agent="debug-agent", task_description="test", max_tokens=2000)
```

Check the response for `tier_summary`:
- `guardrails > 0` AND `declared > 0`: tiered RAG working
- All zeros or missing: clear `__pycache__` and report "RAG needs restart to load tiered context"
- rag_status fails entirely: tell user to run `setup.ps1`

After checks pass, set the sentinel:
```bash
touch "$TEMP/claudeboost_rag_ok" && echo "  RAG: ready"
```

Use `echo "  RAG: failed"` if rag_status fails entirely.

**RAG is non-negotiable.** If RAG fails, boost activation is incomplete.

## Step 2.5: Index ClaudeBoost Codebase (Project RAG)

Keep the codebase index current so `rag_search(scope="codebase")` works against ClaudeBoost's own source:
```bash
echo "$CLAUDEBOOST_HOME"
```

Then call `rag_index_project(project_path=<value from above>)`. Incremental — only changed files re-embed. Report briefly: "X files updated, Y chunks." Skip if RAG failed.

## Step 2.6: Project Index Check

After indexing ClaudeBoost itself, check if there are active project workspaces that need indexing:
```bash
for d in workspace/*/; do if [ -f "${d}context.md" ]; then grep -i "Project:" "${d}context.md" | head -1; fi; done 2>/dev/null | grep -v "N/A" | grep -v "none" | head -5
```

For each project path found:
```bash
PROJECT_PATH="<path from above>" && [ -d "$PROJECT_PATH/workspace/.rag-index" ] && echo "INDEXED" || echo "NOT_INDEXED"
```

**If NOT_INDEXED**: report in Systems Status:
> "Project RAG: not indexed — run `/index-project [path]` to enable vector + graph search"

**If INDEXED**: report "Project RAG: ready — vector + graph search active for [project]."

---

## Step 3: Activate Gas Town (MANDATORY — always prime, auto-init if needed)

```bash
if command -v gt &>/dev/null; then echo "  GT: $(gt --version 2>&1 | head -1)"; GT_OUT=$(gt prime 2>&1); GT_RC=$?; echo "$GT_OUT"; if [ $GT_RC -ne 0 ] && echo "$GT_OUT" | grep -q "not in a Gas Town workspace"; then if [ -d .git ] || git rev-parse --git-dir >/dev/null 2>&1; then echo "  auto-init..."; gt init 2>&1 | tail -5; gt prime 2>&1 | head -5; fi; fi; echo "  GT: ready"; else echo "  GT: NOT FOUND in PATH"; fi
```

GT is "ready" if `command -v gt` succeeds. "failed" ONLY if `gt` is not on PATH.

`gt init` only runs when `gt prime` explicitly reports the cwd is not a workspace AND cwd is a git repo. It's idempotent.

**GT is mandatory.** If not on PATH, warn the user to install it.

## Step 4: Check Hooks

```bash
HOOKS_OK=true && for hook in SessionStart PreToolUse PostToolUse PreCompact UserPromptSubmit Stop; do if python "$CLAUDEBOOST_HOME/scripts/check-hooks.py" "$hook" 2>/dev/null; then true; else echo "  $hook hooks: MISSING"; HOOKS_OK=false; fi; done && if [ "$HOOKS_OK" = false ]; then echo "  [WARN] Some hooks missing — run setup.ps1 to install"; fi
```

Missing hooks warn but don't block boost.

## Step 5: Check Rules

```bash
head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "  rules: ok"
```

If CLAUDE.md doesn't exist, warn.

## Step 5b: Read CONSULT/AUTO Mode

```bash
if [ -f "$CLAUDEBOOST_HOME/state/claudeboost-mode.json" ]; then cat "$CLAUDEBOOST_HOME/state/claudeboost-mode.json"; else echo "mode file missing — defaulting to CONSULT"; fi
```

Clear session-approvals (they don't carry across sessions):
```bash
if [ -f "$CLAUDEBOOST_HOME/state/session-approvals.json" ]; then echo '{"sessionId":"","approvals":[]}' > "$CLAUDEBOOST_HOME/state/session-approvals.json"; fi
```

## Step 6: Workspace Discovery

```bash
mkdir -p workspace && for d in workspace/*/; do if [ -f "${d}context.md" ]; then echo "WORKSPACE: $d"; head -5 "${d}context.md"; echo "---"; fi; done; echo "  workspace: ready"
```

- List each task ID and current status from context.md
- If exactly one workspace exists, read its full `context.md` to restore session state
- If none: "No active workspaces — ready for new work"

## Step 7: Done

```bash
touch "$TEMP/claudeboost_active" && python "$CLAUDEBOOST_HOME/scripts/boost-inline.py" --done
```

**Report format — include ALL of these sections:**

### Systems Status
- RAG: ready/failed (chunk counts)
- Project RAG: indexed (vector + graph) / not indexed
- GT: ready/failed (version)
- Hooks: all 6 types present/missing
- Rules: CLAUDE.md loaded/missing

### Active Workspaces
- List any discovered workspaces with task IDs and status
- If resuming: "Resuming task [id] — last status was [X]"
- If fresh: "No active workspaces"

### Session Directives
- "RAG is active. I will call `rag_context` as Step 1 when spawning agents, and `rag_search` when I need knowledge."
- "Gas Town is active. I will use `gt prime` for workspace init, `gt sling` for cross-session delegation, and `gt handoff` for session transitions."
- If GT failed: append "(GT not found on PATH — install or add to PATH to enable)"

### Collaborative Mode
- **CONSULT (default)**: "I will research, propose via architect-agent (Opus), and ask before any architectural decision. Use `/auto` to bypass for trivial work."
- **AUTO**: "I am in autonomous mode — I will proceed on architectural decisions without consulting. Use `/consult` to re-enable consultation."

### Ready
- Everything passed: "ClaudeBoost is live. Ask me anything or use /spawn-agent to delegate."
- Tiered RAG not loaded: mention it needs a restart
- Privacy auto-fixed: mention what was set
- Anything failed: explain what and how to fix it

Do NOT create the marker file if critical checks (RAG, GT, Rules) failed.
