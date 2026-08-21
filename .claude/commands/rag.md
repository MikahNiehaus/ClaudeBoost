---
description: "Start or reconnect the RAG server and prime the session"
allowed-tools: Bash
---

# /rag — RAG Server Start / Reconnect

## Arguments: $ARGUMENTS

Use this skill to start the RAG server at the beginning of a session, or reconnect after a disconnect. All verification uses the HTTP REST API — no MCP required.

---

## Step 1: Start Both RAG Servers via Supervisor

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/rag-supervisor.py" start
```

This starts the supervisor managing both the main RAG server (port 8612) and clean-rag server (port 8613) with auto restart on crash. If the supervisor is already running, it reports existing status.

If the output says "already running" or shows both servers alive, proceed. If it fails, fall back to direct start:

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/rag-server-start.py"
```

If both fail, stop and report the error.

---

## Step 2: Verify Both Servers via HTTP

Poll main RAG server until ready (up to 60s):

```bash
for attempt in $(seq 1 20); do
  STATUS=$(curl -s --max-time 3 http://127.0.0.1:8613/status)
  echo "$STATUS" | grep -q '"status": *"ready"' && break
  echo "waiting for main RAG server... (attempt $attempt)"
  sleep 3
done
echo "$STATUS"
```

Then check clean-rag server:

```bash
for attempt in $(seq 1 10); do
  CR_STATUS=$(curl -s --max-time 3 http://127.0.0.1:8613/status)
  echo "$CR_STATUS" | grep -q '"status"' && break
  echo "waiting for clean-rag server... (attempt $attempt)"
  sleep 3
done
echo "$CR_STATUS"
```

(`$attempt` is a loop variable and `$STATUS`/`$CR_STATUS` are assigned in the same command, so
bash-guard allows them; curl to 127.0.0.1 is fine.)

If exit code is non-zero, stop and tell the user: "RAG server did not start. Check the terminal for errors or run `python $CLAUDEBOOST_HOME/scripts/rag-server-start.py` manually."

Parse the main RAG JSON output and note:
- `model` — embedding model name
- `embedding_dimensions` — vector size
- `collections.knowledge` — chunk and file counts
- `collections.agents` — chunk and file counts
- `indexed_projects` — any project codebases currently indexed

---

## Step 3: Write the RAG sentinel

The sentinel tells session-primer.py that RAG is verified for this session:

```bash
touch "${TEMP}/claudeboost_rag_ok"
```

(Brace form `${TEMP}` — bash-guard blocks bare `$TEMP` because Claude Code's expansion scanner prompts on it.)

---

## Step 4: Prime the session

Run one real search so the embedding model is loaded and the index is proven
readable:

```bash
curl -s --max-time 15 -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query":"project structure and conventions","sources":["project:'"$CLAUDEBOOST_HOME"'"],"mode":"both","limit":5}'
```

Read the JSON response: a `results` array means RAG is primed; an `error`
field means it failed (note it in the report).

If `results` came back, RAG is fully live. An empty `results` array still counts as
live — the call was served, nothing scored above the threshold. If it errors but
`/status` was healthy, the model may still be warming up — note this in the report
and the user can re-run `/rag` in 30s.

---

## Step 5: Report

**Success:**
```
RAG live — main: port 8612 | knowledge: Xc/Yf agents: Xc/Yf | clean-rag: port 8613 | supervisor: auto restart active | session primed
```

**Model still loading (status was ready but /search timed out):**
```
RAG starting — model loading (~60s). Run /rag again when ready. Status line shows RAG indicator when live.
```

**Failed:**
```
RAG failed — [specific error]. Try: "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/rag-supervisor.py" start in the terminal.
```

---

## Notes

- To do a full session activation (GT, hooks, workspace discovery, etc.), use `/boost` instead.
- To reindex knowledge and agent files after changes, run `/index-boost`.
- The HTTP REST API docs are in `knowledge/rag-http-api.xml`.
