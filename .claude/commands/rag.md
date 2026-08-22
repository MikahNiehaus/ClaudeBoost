---
description: "Start or reconnect the RAG server and prime the session"
allowed-tools: Bash
---

# /rag: RAG Server Start and Reconnect

## Arguments: $ARGUMENTS

Start the RAG server at the beginning of a session, or reconnect after a
disconnect. All verification goes through the HTTP REST API, no MCP required.

There is one server. This command used to start two, a "main" server on 8612
and clean-rag on 8613, through a supervisor. The 8612 server was deleted along
with `mcp-rag-server/`, and both `scripts/rag-supervisor.py` and
`scripts/rag-server-start.py` went with it, so every step below used to invoke
a script that did not exist.

---

## Step 1: Start the server

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/clean-rag/cli/server_ctl.py" start
```

If it reports "already running", proceed. If it fails, stop and report the
error rather than retrying.

---

## Step 2: Verify over HTTP

Poll until ready (up to 60s):

```bash
for attempt in $(seq 1 20); do
  STATUS=$(curl -s --max-time 3 http://127.0.0.1:8613/status)
  echo "$STATUS" | grep -q '"status"' && break
  echo "waiting for the RAG server... (attempt $attempt)"
  sleep 3
done
echo "$STATUS"
```

(`$attempt` is a loop variable and `$STATUS` is assigned in the same command, so
bash-guard allows them. curl to 127.0.0.1 is fine.)

If it never responds, tell the user: "RAG server did not start. Check the
terminal for errors, or run
`python $CLAUDEBOOST_HOME/clean-rag/cli/server_ctl.py start` manually."

Parse the JSON and note:
- `model` — embedding model name
- `embedding_dimensions` — vector size
- `indexed_projects` — project codebases currently indexed

---

## Step 3: Write the RAG sentinel

The sentinel tells session-primer.py that RAG is verified for this session:

```bash
touch "${TEMP}/claudeboost_rag_ok"
```

(Brace form `${TEMP}`, because bash-guard blocks the bare form: Claude Code's
expansion scanner prompts on it.)

---

## Step 4: Prime the session

Run one real search, so the embedding model is loaded and the index is proven
readable:

```bash
curl -s --max-time 15 -X POST http://127.0.0.1:8613/search \
  -H "Content-Type: application/json" \
  -d '{"query":"project structure and conventions","sources":["project:'"$CLAUDEBOOST_HOME"'"],"mode":"both","limit":5}'
```

A `results` array means RAG is primed. An empty `results` array still counts as
live: the call was served, nothing scored above the threshold. An `error` field
means it failed. If it errors while `/status` was healthy, the model is probably
still warming up, so note that and let the user re-run `/rag` in 30s.

---

## Step 5: Report

**Success:**
```
RAG live — port 8613 | indexed projects: N | session primed
```

**Model still loading (status was ready but /search timed out):**
```
RAG starting — model loading (~60s). Run /rag again when ready. The status line shows the RAG indicator when live.
```

**Failed:**
```
RAG failed — [specific error]. Try: "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/clean-rag/cli/server_ctl.py" start in the terminal.
```

---

## Notes

- For a full session activation (hooks, workspace discovery, and the rest), use
  `/boost` instead.
- To index a project, run `/index-project`.
- The search contract is in `CLAUDE.md` under "clean-rag (the search backend,
  port 8613)". The old `knowledge/rag-http-api.xml` was deleted with the
  knowledge base.
