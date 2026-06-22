---
argument-hint: [key] [value]
description: View and edit ClaudeBoost state values — RAG enforcement, CONSULT/AUTO mode, intent override, active workspace.
allowed-tools: Read, Write, Edit, Bash, Glob
---

# /edit-state — ClaudeBoost State Editor

Arguments: `[key] [value]`

Shows all ClaudeBoost state values. Pass a key and value to update one.

Examples:
- `/edit-state` — show all state
- `/edit-state rag-enforcement off` — disable RAG error guard
- `/edit-state rag-enforcement on` — re-enable RAG error guard
- `/edit-state mode auto` — switch to AUTO mode
- `/edit-state mode consult` — switch to CONSULT mode
- `/edit-state intent C:/prj/myproject` — set project path override for this instance
- `/edit-state intent clear` — remove intent override for this instance

---

## Phase 1: Read All State Files

Read each state file from `$CLAUDEBOOST_HOME/state/`:

| File | Key fields |
|------|-----------|
| `claudeboost-mode.json` | mode (CONSULT/AUTO), setAt, reason |
| `rag-enforcement.json` | enabled (true/false), setAt |
| `speak-state.json` | enabled (true/false), voice |
| `intent-override.json` | per-instance project path overrides |
| `ws-instance/` | per-instance active workspace map |

For `ws-instance/`: list all files, read the one for this Claude instance (identified by the node.exe PID in the filename — look for the most recently modified file, or the one whose path matches the current process).

---

## Phase 2: Display

Print a clean state summary:

```
ClaudeBoost State
────────────────────────────────────────────────────

  Mode              CONSULT   (set 2026-06-19 by /consult)
  RAG enforcement   ON        (default)
  TTS               OFF       (voice: en-US-AndrewNeural)

  Active workspace  better-permissions-2026-06-21  [C:/prj/ClaudeBoost]
  Intent override   none  (cwd: C:/prj/ClaudeBoost)

  State dir: C:/prj/ClaudeBoost/state/

To change a value: /edit-state <key> <value>
  Keys: mode (consult|auto), rag-enforcement (on|off), intent (<path>|clear), ws (<workspace-id>|off)
```

---

## Phase 3: Apply Change (only if arguments were provided)

### `mode consult` or `mode auto`
Write to `$CLAUDEBOOST_HOME/state/claudeboost-mode.json`:
```json
{
  "mode": "CONSULT",
  "setAt": "<ISO timestamp>",
  "setBy": "/edit-state",
  "reason": "user request via /edit-state"
}
```
Confirm: "Mode set to CONSULT. Takes effect immediately."

### `rag-enforcement on` or `rag-enforcement off`
Write to `$CLAUDEBOOST_HOME/state/rag-enforcement.json`:
```json
{"enabled": true, "setAt": "<ISO timestamp>", "setBy": "/edit-state"}
```
Confirm: "RAG enforcement ON. rag-error-guard.py will hard-block on RAG errors."
Or: "RAG enforcement OFF. RAG errors will not block — use with care."

### `intent <path>`
Read `$CLAUDEBOOST_HOME/state/intent-override.json` (default `{}`).
Get the current instance ID (from process tree walk or env — same logic as rag-statusline.py).
Set `{instance_id: path}` and write back.
Confirm: "Intent override set: this instance will use <path> as the working project."

### `intent clear`
Read `$CLAUDEBOOST_HOME/state/intent-override.json`.
Remove the entry for this instance ID.
Confirm: "Intent override cleared. Using cwd as project path."

### `ws <workspace-id>`
This is a shortcut for `/ws <workspace-id>`.
Run:
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" <workspace-id>
```
Confirm: "Active workspace set to <workspace-id>."

### `ws off`
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" off
```
Confirm: "Active workspace cleared."

---

## Notes

- State changes to `rag-enforcement` and `mode` take effect immediately on the next prompt.
- Intent override is per-instance — it only affects the current Claude window. Other windows are unaffected.
- To set the intent override for all instances, set key `"default"` in `intent-override.json` manually.
- The intent override is useful when you open Claude in `C:/prj/ClaudeBoost` but are working on `C:/prj/todaymechanic` — set the override so the injector uses the correct project KB and workspace KB.
