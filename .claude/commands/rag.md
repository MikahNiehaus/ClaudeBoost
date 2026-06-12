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
python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; sys.exit(subprocess.run([sys.executable,h+'/scripts/rag-server-start.py']).returncode)"
```

If the output is "already running" or "ready", proceed. If it fails or times out, stop and report the error — do not continue.

---

## Step 2: Verify via HTTP

Poll until ready (up to 60s):

```bash
python3 -c "
import time, json, urllib.request, urllib.error, sys
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8612/status', timeout=3) as r:
            data = json.loads(r.read())
            if data.get('status') == 'ready':
                print(json.dumps(data, indent=2))
                sys.exit(0)
            print('status:', data.get('status', '?'), '-- waiting...')
    except urllib.error.URLError:
        print('waiting for server...')
    time.sleep(3)
print('ERROR: server did not become ready within 60s')
sys.exit(1)
"
```

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
python3 -c "
import json, urllib.request, urllib.error
body = json.dumps({'agent': 'debug-agent', 'task_description': 'session start', 'max_tokens': 2000}).encode()
req = urllib.request.Request('http://127.0.0.1:8612/context', data=body, headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
        if 'error' in data:
            print('context error:', data['error'])
        else:
            print('token_count:', data.get('token_count', '?'))
            print('sources:', len(data.get('sources', [])))
except Exception as e:
    print('context call failed:', e)
"
```

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
RAG failed — [specific error]. Try: python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; sys.exit(subprocess.run([sys.executable,h+'/scripts/rag-server-start.py']).returncode)" in the terminal.
```

---

## Notes

- To do a full session activation (GT, hooks, workspace discovery, etc.), use `/boost` instead.
- To reindex knowledge and agent files after changes, run `/index-boost`.
- The HTTP REST API docs are in `knowledge/rag-http-api.xml`.
