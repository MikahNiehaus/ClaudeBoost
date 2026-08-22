---
argument-hint: "[--diagnose-only]"
description: "Spawn a parallel agent to diagnose and fix clean-rag server issues"
allowed-tools: Agent, Bash, Read
---

# /fix-rag — Clean-RAG Diagnostic and Repair Agent

Arguments: **$ARGUMENTS**

Spawns a parallel background agent that diagnoses and fixes clean-rag server issues (port 8613). The main agent keeps working while the fix runs. Use this when you hit ECONNREFUSED, timeouts, or search errors from the clean-rag server.

---

## Step 1: Parse Arguments

- `--diagnose-only`: report issues without fixing them
- No arguments: diagnose AND fix automatically

Set `DIAGNOSE_ONLY` = true if `--diagnose-only` is in `$ARGUMENTS`, false otherwise.

---

## Step 2: Spawn Background Agent

Spawn a single background agent (Haiku model) with `run_in_background=true`.

The agent prompt must include ALL of the following:

```
You are a diagnostic agent for the clean-rag server (port 8613). Your job is to find what's wrong and fix it.

FIRST ACTION: This is a repair agent. Skip every search call, since the server you would search is the one that may be down. Go straight to diagnosis.

DIAGNOSE_ONLY: [true or false]
CLEAN_RAG_HOME: $CLEAN_RAG_HOME
STATE_DIR: $CLEAN_RAG_HOME/state
SERVER_PORT: $CLEAN_RAG_PORT (default 8613)

## Step 1: Health Check

```bash
curl -s --connect-timeout 5 http://127.0.0.1:8613/status
```

Interpret the result:
- Connection refused or timeout: server is DOWN. Go to Step 2.
- HTTP 200, status "warming_up": server is starting. Wait 30s, retry. If still warming up after 90s total, go to Step 2 (restart).
- HTTP 200, status "ready": server is HEALTHY. Go to Step 3 for deeper checks.
- Any other error: note it, go to Step 2.

## Step 2: Server Recovery

If DIAGNOSE_ONLY is true, report the issue and skip to Step 4.

2a. Check the PID file:
```bash
cat "$CLEAN_RAG_HOME/state/server.json" 2>/dev/null
```

2b. If PID file exists, check if process is alive:
```bash
# On Windows, use tasklist
tasklist /FI "PID eq <pid>" 2>/dev/null
```

2c. Decide action:
- PID file exists + process alive + not responding: kill the process, wait 2s, restart
- PID file exists + process dead: stale PID file. Delete state/server.json, then start
- No PID file: just start

2d. Start the server:
```bash
python "$CLEAN_RAG_HOME/cli/server_ctl.py" start
```

2e. Wait for readiness (up to 60 seconds):
```bash
for i in $(seq 1 12); do
  result=$(curl -s --connect-timeout 5 http://127.0.0.1:8613/status 2>/dev/null)
  if echo "$result" | grep -q '"ready"'; then
    echo "Server is ready"
    break
  fi
  sleep 5
done
```

If still not ready after 60s, check for port conflicts:
```bash
netstat -ano | findstr :8613
```
Report the conflicting process and stop (needs user intervention).

## Step 3: Project Index Health Check

Parse the /status response to get the list of indexed projects. clean-rag searches
projects only now, so there are no topics to check. Each entry lists a project path
and its vector and graph stats.

Run one real search against each project to confirm it returns scored results:
```bash
curl -s -X POST http://127.0.0.1:8613/search -H "Content-Type: application/json" -d '{"query":"test","sources":["project:<abs path>"],"mode":"both","limit":1}'
```

If a project search returns an error (not empty results, but an actual error response):
- The vector index or graph.db may be out of sync with the files on disk
- If DIAGNOSE_ONLY: report which project errored, skip fix
- If fixing: reindex it. Reindex the whole project, or just one file:
```bash
curl -s -X POST http://127.0.0.1:8613/index-project -H "Content-Type: application/json" -d '{"project_path":"<abs path>","force":true}'
# or a single file:
curl -s -X POST http://127.0.0.1:8613/reindex-file -H "Content-Type: application/json" -d '{"file_path":"<abs path>"}'
```

## Step 4: Report

End your response with ## Summary (under 300 words):
- Server status: running / recovered / failed
- Recovery action taken: none / restarted / killed+restarted / PID cleanup
- Projects checked: N total
- Projects healthy: N
- Projects reindexed: N (list which ones)
- Projects failed: N (list which ones and why)
- Issues needing user intervention: (port conflicts, missing models, etc.)
- Time taken for recovery: Ns
```

After spawning, tell the user:
"Background diagnostic agent spawned for clean-rag server. You'll be notified when it completes."

---

## What's Next After /fix-rag

| If... | Then run... |
|-------|------------|
| Server is fixed and a project needs reindexing | `POST /index-project` with `{"project_path":"<abs path>","force":true}` |
| Server keeps failing | Check `clean-rag/state/server.json` and server logs manually |
| You want to verify the fix | `curl http://127.0.0.1:8613/status` |
