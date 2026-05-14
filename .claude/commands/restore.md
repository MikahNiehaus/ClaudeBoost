---
description: Restore context from the last /clear-safe handoff
argument-hint: [workspace-id]
---

# /restore — Post-Clear Context Restore

Manually restores saved context from `state/handoff-latest.json`.
Use this after `/clear` when the automatic restore did not fire (e.g., the
`clear-pending.json` flag expired, or `/clear` was run without `/clear-safe`).

If `$ARGUMENTS` is provided, treat it as a workspace ID override.

---

## Step 1 — Load handoff state

Read `$CLAUDEBOOST_HOME/state/handoff-latest.json`.

If the file does not exist:
> No saved handoff found at `state/handoff-latest.json`. Nothing to restore.

Extract:
- `active_workspace` — workspace ID that was active at save time
- `workspace_memo` — full memo text
- `timestamp` — when the save occurred

If `$ARGUMENTS` is non-empty, override `active_workspace` with the provided value.

## Step 2 — Load full context.md

Resolve the workspace path for `[active_workspace]`:

1. Check the registry first:
   ```bash
   python3 "$CLAUDEBOOST_HOME/scripts/register-workspace.py" --get [active_workspace] 2>/dev/null
   ```
   If a path is returned, use `[registry_path]/context.md`.

2. Otherwise fall back to the ClaudeBoost-local path:
   `$CLAUDEBOOST_HOME/workspace/[active_workspace]/context.md`

Read the resolved `context.md` if it exists.
This is the authoritative source — the workspace_memo is a snapshot; context.md
may have been updated since.

## Step 3 — Present restored context

Print:

```
/restore — Context Restored
===========================

Workspace  : [active_workspace]
Saved at   : [timestamp]

[workspace_memo contents]
```

If context.md was read and differs meaningfully from the memo, also show:

```
context.md (current)
====================
[context.md contents]
```

## Step 4 — Resume

Tell the user:

> Context restored from `state/handoff-latest.json`.
> Active workspace: **[active_workspace]** (`[resolved context.md path]`)
> Continue from: [Next Step from context.md or workspace_memo]
>
> If this is the wrong workspace, run `/restore [workspace-id]` with the correct ID.
