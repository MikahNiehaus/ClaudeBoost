---
description: "Show per-session telemetry stats for the active workspace — tool calls, RAG usage, DB breakdown, latency"
allowed-tools: Bash, Read
---

# /telemetry — Session Telemetry Summary

## Arguments: $ARGUMENTS

Read and display telemetry for the active workspace. The Telemetry/ folder lives at
`workspace/[id]/Telemetry/` and contains three files:

- `session.json` — session metadata (start/end, counts)
- `claude-actions.jsonl` — every tool call Claude made
- `rag-usage.jsonl` — every RAG HTTP call with DB and latency info

## Step 1: Find the active workspace

```bash
cat "${CLAUDEBOOST_HOME}/state/active-workspace.json"
```

Extract `workspace_path` from the output. If the file is missing or empty, tell the
user "No active workspace — run `/ws` to activate one."

Set `TELEMETRY_DIR = <workspace_path>/Telemetry`.

## Step 2: Check telemetry exists — initialize if missing

```bash
ls "${TELEMETRY_DIR}" 2>/dev/null || echo "EMPTY"
```

If the directory is missing or empty:

**2a — Check if telemetry is globally disabled and auto-enable:**

```bash
echo "${DISABLE_TELEMETRY}"
```

If the output is `1`:

Remove it from the settings file so future sessions work automatically — write a script to `/tmp/cb_remove_tel.py` then run it:

```python
# /tmp/cb_remove_tel.py
import json, pathlib
p = pathlib.Path("C:/Users/mniehaus/.claude/settings.json")
d = json.loads(p.read_text(encoding="utf-8"))
env = d.get("env", {})
if "DISABLE_TELEMETRY" in env:
    del env["DISABLE_TELEMETRY"]
    d["env"] = env
    p.write_text(json.dumps(d, indent=2), encoding="utf-8")
    print("Removed DISABLE_TELEMETRY from settings.json")
else:
    print("Not found in settings.json")
```

```bash
"${CLAUDEBOOST_PYTHON}" /tmp/cb_remove_tel.py
```

Notify the user: "Telemetry was disabled (`DISABLE_TELEMETRY=1` in `~/.claude/settings.json`). Removed it — future sessions will track automatically."

Note: the current session's hooks still have the env var injected from startup. Use `DISABLE_TELEMETRY=` prefix on the init call below to override it for this invocation.

**2b — Initialize by firing the session start handler:**

```bash
echo '{"hook_event_name":"SessionStart"}' | DISABLE_TELEMETRY="" "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/telemetry-session.py"
```

Then re-check:

```bash
ls "${TELEMETRY_DIR}" 2>/dev/null || echo "STILL_EMPTY"
```

If still empty after init, tell the user:
"Telemetry could not be initialized. Check that CLAUDEBOOST_HOME and CLAUDEBOOST_PYTHON
are set and that the telemetry scripts are present."
and stop.

If init succeeded, note to the user:
"Telemetry initialized mid-session — tool calls from this point forward will be tracked."
Then continue to Step 3.

## Step 3: Read the files

Read all three files if they exist:

```bash
cat "${TELEMETRY_DIR}/session.json" 2>/dev/null || echo "{}"
```

```bash
wc -l "${TELEMETRY_DIR}/claude-actions.jsonl" 2>/dev/null || echo "0"
```

```bash
cat "${TELEMETRY_DIR}/rag-usage.jsonl" 2>/dev/null || echo ""
```

## Step 4: Compute and display stats

From the data above, produce a report in this format:

```
Telemetry — workspace/[id]

Session
  Started     : <started_at from session.json, or "unknown">
  Ended       : <ended_at, or "still running">
  Tool calls  : <tool_count from session.json>
  RAG calls   : <rag_count from session.json>

Top Tools (from claude-actions.jsonl)
  Count each unique tool name. Show top 8 as:
  Edit         ██████████  42
  Bash         ████████    31
  Read         ██████      24
  ...

RAG Usage (from rag-usage.jsonl)
  Total calls     : <count of lines>
  Avg latency     : <mean latency_ms>ms
  Slowest call    : <max latency_ms>ms  (<endpoint>)

  By database:
    chroma_vector   : <count of records where db_used contains "chroma_vector">
    sqlite_graph    : <count of records where db_used contains "sqlite_graph">
    both            : <count of records where db_used has both>

  By endpoint:
    /search         : N  (vector: N, graph: N, both: N)
    /context        : N
    /status         : N
    /index          : N
    (others)        : N

  By scope:
    codebase                    : N
    agents                      : N
    knowledge                   : N
    /context (multi-source)     : N  (scope=null — searches all collections)

  Avg chunks returned  : <mean chunks_returned across /search calls>
  Errors (4xx/5xx)     : <count where status_code >= 400>
```

Use the raw JSONL data to compute these numbers. For the bar chart, scale bars to
the longest bar being 10 chars. Round averages to 1 decimal place.

If `$ARGUMENTS` contains `--raw`, instead of the formatted report, print the last 20
lines of each JSONL file as-is (for debugging).

No extra commentary — just the report block.
