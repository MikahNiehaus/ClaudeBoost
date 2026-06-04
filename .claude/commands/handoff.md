---
description: Save session state and prepare for a fresh context
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(python -c *)
argument-hint: [message]
---

# Handoff — Save State for a Fresh Session

Save your current workspace context so it can be restored in the next session.

Arguments: $ARGUMENTS

## What This Does

Saves your active workspace context and conversation highlights to
`state/handoff-latest.json`. When you start a fresh session and run `/boost` or
`/restore`, ClaudeBoost reads that file and restores where you left off.

Use this when your context is getting long and you want a clean start without
losing your place in a task.

---

## Steps

### 1. Save workspace state

```bash
python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; subprocess.run([sys.executable,h+'/scripts/session-clear-save.py'])" 2>/dev/null || true
```

### 2. If a message was provided, store it in the handoff file

```bash
python3 -c "
import json, os, sys
from pathlib import Path
home = os.environ.get('CLAUDEBOOST_HOME', '')
f = Path(home) / 'state' / 'handoff-latest.json'
msg = '''$ARGUMENTS'''.strip()
if f.exists() and msg:
    d = json.loads(f.read_text(encoding='utf-8'))
    d['handoff_message'] = msg
    f.write_text(json.dumps(d, indent=2), encoding='utf-8')
    print('Handoff message saved.')
"
```

### 3. Report to user

Tell the user:
- Which workspace was active (task ID and status from the saved state)
- That they can run `/clear` now to reset context
- That running `/boost` or `/restore` in the next session will pick up where this one left off

---

**Next step:** Run `/clear` to reset context, then start a new session and run `/boost` to restore.
