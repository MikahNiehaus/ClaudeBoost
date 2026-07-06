---
description: "Start, stop, or check clean-rag research enforcement server (port 8613)"
allowed-tools: Bash
---

# /clean-rag-server — Clean-RAG Server Control

## Arguments: $ARGUMENTS (start | stop | status)

Use this skill to manage the clean-rag research enforcement server. This server powers proof-gating for edits and proof file verification.

---

## Step 1: Parse Arguments

```bash
ACTION="${1:-status}"
case "$ACTION" in
  start|stop|status) ;;
  *)
    echo "Usage: /clean-rag-server [start|stop|status]"
    echo "  start  — Start the clean-rag server (port 8613)"
    echo "  stop   — Stop the clean-rag server"
    echo "  status — Check if the server is running"
    exit 0
    ;;
esac
```

---

## Step 2: Run Server Control

```bash
"${CLAUDEBOOST_PYTHON}" "${CLEAN_RAG_HOME}/cli/server_ctl.py" "$ACTION"
```

**Output interpretation:**
- **start**: Reports PID and port, waits for readiness
- **stop**: Reports termination, cleans up PID file
- **status**: Shows embedding models, topics, projects, uptime

If the server fails to start or responds with an error, report the specific error to the user.

---

## Step 3: Verify (for start action only)

If action was `start`, verify the server responded:

```bash
if [ "$ACTION" = "start" ]; then
  for attempt in $(seq 1 10); do
    HTTP_STATUS=$(curl -s --max-time 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:8613/status)
    if [ "$HTTP_STATUS" = "200" ]; then
      echo "✓ clean-rag server is ready (port 8613)"
      exit 0
    fi
    if [ "$attempt" -lt 10 ]; then
      sleep 1
    fi
  done
  echo "⚠ Server process started but not responding yet (model loading?). Try /clean-rag-server status in 30 seconds."
fi
```

---

## Report

**Success (start):**
```
clean-rag server started on port 8613  |  ready for proof requests
```

**Success (stop):**
```
clean-rag server stopped
```

**Success (status):**
```
[Show output from server_ctl.py status command — embedding models, topics, uptime]
```

**Failed:**
```
clean-rag server error: [specific error message]
```

---

## What Next

- **To index new research**: `/index-boost` (ClaudeBoost knowledge) or `/index-project <path>` (project codebase)
- **To verify a proof file**: Check clean-rag server logs at `$CLEAN_RAG_HOME/server/logs/` if available
- **To check server health**: Run `/clean-rag-server status` again
