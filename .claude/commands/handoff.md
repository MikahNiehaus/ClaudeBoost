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
`/boost`, ClaudeBoost reads that file and restores where you left off.

Use this when your context is getting long and you want a clean start without
losing your place in a task.

---

## Steps

### 1. Save workspace state

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/session-clear-save.py" 2>/dev/null || true
```

### 2. If a message was provided, store it in the handoff file

If `$ARGUMENTS` is non-empty, add it to the handoff state with the file tools (no
shell python — bash-guard blocks multiline `python -c`):

1. **Read** `state/handoff-latest.json` (under CLAUDEBOOST_HOME). If it doesn't
   exist, skip this step.
2. **Write** it back with a `"handoff_message"` field set to the trimmed
   `$ARGUMENTS` text, preserving the other fields.
3. Confirm "Handoff message saved."

### 3. Report to user

Tell the user:
- Which workspace was active (task ID and status from the saved state)
- That they can run `/clear` now to reset context
- That running `/boost` in the next session will pick up where this one left off

---

**Next step:** Run `/clear` to reset context, then start a new session and run `/boost` to restore.


---

## Phase 0: Workspace Detection

**Workspace detection (run before any other action):**

Run `get-active-workspace.py` to get the active workspace for this Claude
instance — matches the blue "WS XXXX" status bar (per-instance, not the
stale shared global file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace
than what the script returned, print:
`[handoff] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.

