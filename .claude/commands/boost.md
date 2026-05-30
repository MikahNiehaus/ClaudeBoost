---
description: Activate ClaudeBoost - start RAG HTTP server, prime GT, and load session state
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Step 0: Banner and Clear Caches

Print the header, then clear Python bytecode caches:
```bash
python "$CLAUDEBOOST_HOME/scripts/boost-inline.py" && find "$CLAUDEBOOST_HOME/mcp-rag-server" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null; echo "  caches cleared"
```

## Step 1: Verify Privacy (auto-fix)

```bash
FIXED="" && if [ -z "$DISABLE_TELEMETRY" ]; then python -c "import subprocess; subprocess.run(['python', '-c', 'import winreg' ], capture_output=True) " 2>/dev/null; export DISABLE_TELEMETRY=1; FIXED="$FIXED DISABLE_TELEMETRY"; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then export DISABLE_ERROR_REPORTING=1; FIXED="$FIXED DISABLE_ERROR_REPORTING"; fi && if [ -n "$FIXED" ]; then echo "  auto-fixed:$FIXED"; fi && echo "  privacy: ok"
```

## Step 2: Start RAG HTTP Server (MANDATORY)

The RAG server runs as a persistent HTTP daemon on port 8612. Start it if not already running:
```bash
python "$CLAUDEBOOST_HOME/scripts/rag-server-start.py"
```

If the script prints "already running" or "ready" — proceed. If it fails after 60s, run `/mcp` to check MCP connection, then retry.

Call `rag_status` to verify the server is connected and has indexed content.

Then **actively load RAG context** — this primes the session:
```
rag_context(agent="debug-agent", task_description="test", max_tokens=2000)
```

Check the response for `tier_summary`:
- `guardrails > 0` AND `declared > 0`: tiered RAG working
- All zeros or `tier_errors` present: server warming up — wait 30s and retry rag_context
- `rag_status` fails entirely: tell user to run `setup.ps1`

The status line will show `RAG ●` (green) when live and `RAG ○` (yellow) while the model loads.

**RAG is non-negotiable.** If the server won't start, stop and tell the user.

## Step 2.5: Index ClaudeBoost Codebase (Project RAG)

Keep the ClaudeBoost codebase index current so `rag_search(scope="codebase")` works:
```bash
echo "$CLAUDEBOOST_HOME"
```

Call `rag_index_project(project_path=<value from above>)`. Incremental — only re-embeds changed files. Skip if RAG failed in Step 2.

Also index memories if not already done:
```
rag_index_memories()
```

Report: "X files updated, Y chunks, Z/W graph edges resolved." Check `rag_status` for ClaudeBoost project entry.

## Step 2.6: Project Index Check

Check if active project workspaces have their code indexed:
```bash
for d in workspace/*/; do if [ -f "${d}context.md" ]; then grep -i "Project:" "${d}context.md" | head -1; fi; done 2>/dev/null | grep -v "N/A" | grep -v "none" | head -5
```

For each project path found, call `rag_status` and check if that project appears in `indexed_projects`.

**If not indexed**: report "Project RAG: not indexed — run `/index-project [path]`"
**If indexed**: report file/chunk/graph counts and set the project RAG sentinel:
```bash
touch "$TEMP/claudeboost_project_rag_ok"
```

---

## Step 3: Activate Gas Town (MANDATORY — always prime, auto-init if needed)

```bash
if command -v gt &>/dev/null; then echo "  GT: $(gt --version 2>&1 | head -1)"; GT_OUT=$(gt prime 2>&1); GT_RC=$?; echo "$GT_OUT"; if [ $GT_RC -ne 0 ] && echo "$GT_OUT" | grep -q "not in a Gas Town workspace"; then if [ -d .git ] || git rev-parse --git-dir >/dev/null 2>&1; then echo "  auto-init..."; gt init 2>&1 | tail -5; gt prime 2>&1 | head -5; fi; fi; echo "  GT: ready"; else echo "  GT: NOT FOUND in PATH"; fi
```

GT is "ready" if `command -v gt` succeeds. "failed" ONLY if not on PATH.
`gt init` only runs when `gt prime` says the cwd is not a workspace AND it's a git repo.

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
mkdir -p workspace && for d in workspace/*/; do if [ -f "${d}context.md" ]; then STATUS=$(grep -i "^## Status" -A1 "${d}context.md" | tail -1); echo "$STATUS" | grep -qiE "in progress|plan_ready|implemented|blocked" && echo "WORKSPACE: $d | $STATUS"; fi; done; echo "  workspace: ready"
```

- Only show workspaces with status: IN PROGRESS, PLAN_READY, IMPLEMENTED, or BLOCKED
- If exactly one active workspace: read its full `context.md` to restore session state
- If none: "No active workspaces — ready for new work"

## Step 7: Done

```bash
python "$CLAUDEBOOST_HOME/scripts/boost-inline.py" --done
```

**Report format — include ALL of these sections:**

### Systems Status
- RAG: ready/failed — HTTP server port 8612 (knowledge: X chunks/Y files, agents: X chunks/Y files)
- ClaudeBoost index: X files, Y chunks, Z/W graph edges resolved
- Memories: X memories indexed (or "not indexed — run rag_index_memories")
- Project RAG: ready (files, chunks, edges) / not indexed
- GT: ready/failed (version)
- Hooks: all 6 types present/missing
- Rules: CLAUDE.md loaded/missing

### Active Workspaces
- List any discovered workspaces with task IDs and status
- If resuming: "Resuming task [id] — last status was [X]"
- If fresh: "No active workspaces"

### Session Directives
- "RAG is active on HTTP port 8612. I will call `rag_context` first when spawning agents, and `rag_search` when I need knowledge."
- "Gas Town is active. I will use `gt prime`, `gt sling`, and `gt handoff` for session transitions."
- If GT failed: append "(GT not found on PATH — install or add to PATH to enable)"

### Collaborative Mode
- **CONSULT (default)**: "I will research, propose via architect-agent (Opus), and ask before any architectural decision. Use `/auto` to bypass."
- **AUTO**: "Autonomous mode — I will proceed on architectural decisions without consulting. Use `/consult` to restore."

### Ready
- Everything passed: "ClaudeBoost is live. Status line shows RAG ● when server is healthy."
- RAG warming up: "RAG ○ — model loading, will be ready in ~60s. Status line will update."
- Anything failed: explain what and how to fix it
