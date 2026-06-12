---
description: "Start or reconnect the RAG server and prime the session"
allowed-tools: Bash
---

# /rag — RAG Server Start / Reconnect

## Arguments: $ARGUMENTS

Use this skill to start the RAG server at the beginning of a session, or reconnect after a disconnect. All verification uses the HTTP REST API — no MCP required.

---

## Step 1: Start the RAG HTTP Server

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/rag-server-start.py"
```

If the output is "already running" or "ready", proceed. If it fails or times out, stop and report the error — do not continue.

---

## Step 2: Verify via HTTP

Poll until ready (up to 60s):

```bash
for attempt in $(seq 1 20); do
  STATUS=$(curl -s --max-time 3 http://127.0.0.1:8612/status)
  echo "$STATUS" | grep -q '"status": *"ready"' && break
  echo "waiting for server... (attempt $attempt)"
  sleep 3
done
echo "$STATUS"
```

(`$attempt` is a loop variable and `$STATUS` is assigned in the same command, so
bash-guard allows them; curl to 127.0.0.1 is fine. If the loop ends without
`ready`, the last `echo` shows whatever the server returned.)

If exit code is non-zero, stop and tell the user: "RAG server did not start. Check the terminal for errors or run `python $CLAUDEBOOST_HOME/scripts/rag-server-start.py` manually."

Parse the JSON output and note:
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

Call the context endpoint to load knowledge into the conversation:

```bash
curl -s --max-time 15 -X POST http://127.0.0.1:8612/context -H "Content-Type: application/json" -d '{"agent":"debug-agent","task_description":"session start","max_tokens":2000}'
```

Read the JSON response: a `token_count` field means RAG is primed; an `error`
field means it failed (note it in the report).

If it returns a token_count, RAG is fully live. If it errors but `/status` was healthy, the model may still be warming up — note this in the report and the user can re-run `/rag` in 30s.

---

## Step 5: Report

**Success:**
```
RAG live — HTTP port 8612  |  knowledge: Xc/Yf  agents: Xc/Yf  |  session primed
```

**Model still loading (status was ready but /context timed out):**
```
RAG starting — model loading (~60s). Run /rag again when ready. Status line shows RAG indicator when live.
```

**Failed:**
```
RAG failed — [specific error]. Try: "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/rag-server-start.py" in the terminal.
```

---

## Notes

- To do a full session activation (GT, hooks, workspace discovery, etc.), use `/boost` instead.
- To reindex knowledge and agent files after changes, run `/index-boost`.
- The HTTP REST API docs are in `knowledge/rag-http-api.xml`.
