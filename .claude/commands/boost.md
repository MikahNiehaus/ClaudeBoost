---
description: "<true|false|verify>  true: always-on rules only  |  false: off  |  verify: full RAG activation"
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Arguments: $ARGUMENTS

Check $ARGUMENTS first.

If $ARGUMENTS is "true":
```bash
echo '{"mode":"true"}' > "$CLAUDEBOOST_HOME/state/boost-injection.json"
```
Report: "Switched to: ON. Always-on rules will inject on every prompt. RAG standing orders are skipped until you run /boost verify." Then stop — do not run the full activation flow.

If $ARGUMENTS is "false":
```bash
echo '{"mode":"false"}' > "$CLAUDEBOOST_HOME/state/boost-injection.json"
```
Report: "Switched to: OFF. No rules will inject until you run /boost true or /boost verify." Then stop — do not run the full activation flow.

If $ARGUMENTS is "verify" or empty — write verify state and run the full activation flow below:
```bash
echo '{"mode":"verify"}' > "$CLAUDEBOOST_HOME/state/boost-injection.json"
```

---

## Step 0: Banner and Clear Caches

Print the header, then clear Python bytecode caches:
```bash
python -c "
import os, subprocess, sys, shutil
from pathlib import Path
h = os.environ['CLAUDEBOOST_HOME']
subprocess.run([sys.executable, h+'/scripts/boost-inline.py'])
for p in Path(h, 'mcp-rag-server').rglob('__pycache__'):
    shutil.rmtree(p, ignore_errors=True)
print('  caches cleared')
"
```

## Step 1: Verify Privacy (auto-fix)

```bash
FIXED="" && if [ -z "$DISABLE_TELEMETRY" ]; then python -c "import subprocess; subprocess.run(['python', '-c', 'import winreg' ], capture_output=True) " 2>/dev/null; export DISABLE_TELEMETRY=1; FIXED="$FIXED DISABLE_TELEMETRY"; fi && if [ -z "$DISABLE_ERROR_REPORTING" ]; then export DISABLE_ERROR_REPORTING=1; FIXED="$FIXED DISABLE_ERROR_REPORTING"; fi && if [ -n "$FIXED" ]; then echo "  auto-fixed:$FIXED"; fi && echo "  privacy: ok"
```

## Step 2: Start RAG HTTP Server (MANDATORY)

The RAG server runs as a persistent HTTP daemon on port 8612. Start it if not already running:
```bash
python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; sys.exit(subprocess.run([sys.executable,h+'/scripts/rag-server-start.py']).returncode)"
```

If the script prints "already running" or "ready" — proceed. If it fails after 60s, stop and tell the user.

Verify via HTTP:
```bash
python3 -c "
import json, urllib.request, sys, time
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8612/status', timeout=3) as r:
            data = json.loads(r.read())
            if data.get('status') == 'ready':
                print(json.dumps(data, indent=2)); sys.exit(0)
            print('waiting:', data.get('status'))
    except: print('waiting...')
    time.sleep(3)
sys.exit(1)
"
```

If the server is ready, write the RAG sentinel and prime the session:
```bash
touch "$TEMP/claudeboost_rag_ok"
```

Then load RAG context via HTTP:
```bash
python3 -c "
import json, urllib.request
body = json.dumps({'agent': 'debug-agent', 'task_description': 'session start', 'max_tokens': 2000}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/context', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.loads(r.read())
    print('token_count:', data.get('token_count'), 'sources:', len(data.get('sources', [])))
"
```

If this returns a token_count, tiered RAG is working. If it errors, the model may still be loading — wait 30s and retry.

The status line will show `RAG ●` (green) when live and `RAG ○` (yellow) while the model loads.

**RAG is non-negotiable.** If the server won't start, stop and tell the user.

## Step 2.5: Index ClaudeBoost Codebase (Project RAG)

Keep the ClaudeBoost codebase index current so `POST http://127.0.0.1:8612/search with scope="codebase"` works:
```bash
echo "$CLAUDEBOOST_HOME"
```

Call `POST http://127.0.0.1:8612/index` with `{"project_path":"<value from above>"}`. Incremental — only re-embeds changed files. Skip if RAG failed in Step 2.

Also index memories via HTTP:
```bash
python3 -c "
import json, urllib.request
body = json.dumps({'scope': 'memories'}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/index', data=body, headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req, timeout=30) as r:
    print(json.loads(r.read()))
"
```

Report: "X files updated, Y chunks, Z/W graph edges resolved." Check `GET http://127.0.0.1:8612/status` for ClaudeBoost project entry.

## Step 2.6: Project Index Check

Check if active project workspaces have their code indexed:
```bash
for d in workspace/*/; do if [ -f "${d}context.md" ]; then grep -i "Project:" "${d}context.md" | head -1; fi; done 2>/dev/null | grep -v "N/A" | grep -v "none" | head -5
```

For each project path found, call `GET http://127.0.0.1:8612/status` and check if that project appears in `indexed_projects`.

**If not indexed**: report "Project RAG: not indexed — run `/index-project [path]`"
**If indexed**: report file/chunk/graph counts.

---

## Step 3: Check Hooks

```bash
HOOKS_OK=true && for hook in SessionStart PreToolUse PostToolUse PreCompact UserPromptSubmit Stop; do if python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; sys.exit(subprocess.run([sys.executable,h+'/scripts/check-hooks.py','$hook'],capture_output=True).returncode)" 2>/dev/null; then true; else echo "  $hook hooks: MISSING"; HOOKS_OK=false; fi; done && if [ "$HOOKS_OK" = false ]; then echo "  [WARN] Some hooks missing — run setup.py to install"; fi
```

Missing hooks warn but don't block boost.

## Step 4: Check Rules

```bash
head -5 ~/.claude/CLAUDE.md 2>/dev/null && echo "  rules: ok"
```

If CLAUDE.md doesn't exist, warn.

## Step 4b: Read CONSULT/AUTO Mode

```bash
if [ -f "$CLAUDEBOOST_HOME/state/claudeboost-mode.json" ]; then cat "$CLAUDEBOOST_HOME/state/claudeboost-mode.json"; else echo "mode file missing — defaulting to CONSULT"; fi
```

Clear session-approvals (they don't carry across sessions):
```bash
if [ -f "$CLAUDEBOOST_HOME/state/session-approvals.json" ]; then echo '{"sessionId":"","approvals":[]}' > "$CLAUDEBOOST_HOME/state/session-approvals.json"; fi
```

## Step 4c: MCP Debugger Check

Verify `mcp-debugger` is registered and connected:
```bash
claude mcp list 2>&1 | grep -i "mcp-debugger"
```

- If the line contains `✓ Connected` — report "mcp-debugger: connected"
- If the line is missing entirely — report "mcp-debugger: NOT registered — run: `claude mcp add mcp-debugger --scope user -- npx -y @debugmcp/mcp-debugger stdio`"
- If the line shows an error — report "mcp-debugger: registered but failed to start — check Node 22+ is installed"

---

## Step 5: Workspace Discovery

```bash
mkdir -p workspace && for d in workspace/*/; do if [ -f "${d}context.md" ]; then STATUS=$(grep -i "^## Status" -A1 "${d}context.md" | tail -1); echo "$STATUS" | grep -qiE "in progress|plan_ready|implemented|blocked" && echo "WORKSPACE: $d | $STATUS"; fi; done; echo "  workspace: ready"
```

- Only show workspaces with status: IN PROGRESS, PLAN_READY, IMPLEMENTED, or BLOCKED
- If exactly one active workspace: read its full `context.md` to restore session state
- If none: "No active workspaces — ready for new work"

## Step 6: Done

```bash
python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; sys.exit(subprocess.run([sys.executable,h+'/scripts/boost-inline.py','--done']).returncode)"
```

**Report format — include ALL of these sections:**

### Systems Status
- RAG: ready/failed — HTTP server port 8612 (knowledge: X chunks/Y files, agents: X chunks/Y files)
- ClaudeBoost index: X files, Y chunks, Z/W graph edges resolved
- Memories: X memories indexed (or "not indexed — run rag_index_memories")
- Project RAG: ready (files, chunks, edges) / not indexed
- MCP Debugger: connected / not registered / failed (Step 4c result)
- Hooks: all 6 types present/missing
- Rules: CLAUDE.md loaded/missing

### Active Workspaces
- List any discovered workspaces with task IDs and status
- If resuming: "Resuming task [id] — last status was [X]"
- If fresh: "No active workspaces"

### Session Directives
- "RAG is active on HTTP port 8612. I will call POST /context first when spawning agents, and POST /search when I need knowledge."

### Collaborative Mode
- **CONSULT (default)**: "I will research, propose via architect-agent (Opus), and ask before any architectural decision. Use `/auto` to bypass."
- **AUTO**: "Autonomous mode — I will proceed on architectural decisions without consulting. Use `/consult` to restore."

### Ready
- Everything passed: "ClaudeBoost is live. Status line shows RAG ● when server is healthy."
- RAG warming up: "RAG ○ — model loading, will be ready in ~60s. Status line will update."
- Anything failed: explain what and how to fix it
