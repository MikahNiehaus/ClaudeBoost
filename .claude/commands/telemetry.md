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

## Step 2: Check telemetry exists

```bash
ls "${TELEMETRY_DIR}" 2>/dev/null || echo "EMPTY"
```

If the directory is missing or empty, tell the user:
"No telemetry yet for this workspace. Telemetry is written automatically once the
updated hooks are active (run `python scripts/setup.py` to install them)."

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
    codebase        : N
    agents          : N
    knowledge       : N
    (unset)         : N

  Avg chunks returned  : <mean chunks_returned across /search calls>
  Errors (4xx/5xx)     : <count where status_code >= 400>
```

Use the raw JSONL data to compute these numbers. For the bar chart, scale bars to
the longest bar being 10 chars. Round averages to 1 decimal place.

If `$ARGUMENTS` contains `--raw`, instead of the formatted report, print the last 20
lines of each JSONL file as-is (for debugging).

No extra commentary — just the report block.
