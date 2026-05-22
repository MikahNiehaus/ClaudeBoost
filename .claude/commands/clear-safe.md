---
description: Pre-flight verified context clear — saves workspace state before /clear so the next session can restore it
---

# /clear-safe — Pre-flight verified context clear

Verifies workspace state is captured, shows exactly what survives the clear, and
saves the active workspace so the next session restores only the relevant context.
Does NOT run /clear itself — you confirm and type /clear.

## Instructions

**Step 1 — Detect active workspace**

Read `$CLAUDEBOOST_HOME/state/active-workspace.json` (field: `workspace`).

**Staleness guard:** `active-workspace.json` is only written at `/clear-safe` time, so it may
reflect a *previous* session's workspace. To check for a newer workspace without bash:

1. Use Glob with pattern `workspace/*/context.md` in the ClaudeBoost-local dir — Glob returns
   files sorted by modification time (most recent first). The first result is the newest.
2. Also read `$CLAUDEBOOST_HOME/state/workspaces.json` (Read tool) — each key is a task ID with
   a `workspace_path` field. For any project-scoped workspace paths, use Glob with pattern
   `[workspace_path]/context.md` to check if those exist.
3. Compare the stored workspace against the Glob winner. If the Glob winner differs from the
   stored value AND the stored workspace's context.md appears near the bottom of the Glob results
   (i.e., older), prefer the Glob winner and tell the user:
   > "state/active-workspace.json says **[stored]**, but **[mtime-winner]** appears more recent.
   > Using **[mtime-winner]** — correct this before proceeding if wrong."

If no workspace exists at all: skip to Step 4.

**Step 2 — Read and audit context.md**

Read the active workspace's `context.md` in full (create it as an empty file if missing).

Check for ALL of the following:

| Check | What to look for |
|-------|-----------------|
| Current status | A section named "Status", "Progress", or similar with a non-empty value |
| Next step | A specific, actionable next step (not "TBD" or blank) |
| Key decisions | At least one decision or constraint documented |
| Recency | File contains a "Last updated" date of today, OR was clearly written/edited this session |

**If any checks fail — draft missing sections, do NOT block:**

1. Note exactly which sections are missing or stale.
2. Draft the missing content using what you know from this session:
   - **Status**: summarize what was accomplished this session in 1-2 sentences
   - **Next step**: the most concrete next action based on where the session ended
   - **Key decisions**: list the key technical choices made this session (file changed, approach picked, bug fixed, etc.)
   - **Recency**: if the file is stale but content is correct, just touch it — update the timestamp by appending a blank line then removing it, or re-save the file as-is with a "Last updated" note
3. Write the drafted sections into `context.md`. Preserve any existing content — only ADD the missing sections.
4. Tell the user: "I drafted [missing sections] into context.md from session context — review and edit if anything is wrong, then I'll show the survival summary."
5. Re-read context.md and re-run all checks.
6. If all checks now pass: continue to Step 3.
7. If a check still fails after drafting (e.g., you genuinely don't know what the next step is): ask the user to fill in only that specific field. Do not block on everything — only ask about what you couldn't determine.

**Step 3 — Show survival summary**

Print a clear block showing what the next session will see:

```
/clear-safe pre-flight

Active workspace : [task-id]
context.md age   : [N minutes ago]

What survives /clear
====================
Status    : [one-line from context.md]
Next step : [next step from context.md]
Decisions : [count] documented

Scoped restore: next session injects ONLY this workspace's context.
```

**Step 4 — Save active workspace to state**

Write `$CLAUDEBOOST_HOME/state/active-workspace.json`:
```json
{"workspace": "[task-id]"}
```

If there is no active workspace, write `{"workspace": ""}`.

**Step 4b — Save handoff and arm the clear-pending flag.**

Write `$CLAUDEBOOST_HOME/state/handoff-latest.json` directly using the Write tool:

```json
{
  "session_id": "manual-clear-safe",
  "timestamp": "[current UTC ISO timestamp]",
  "trigger": "SessionEnd(clear)",
  "active_workspace": "[task-id]",
  "workspace_memo": "# Clear Handoff Memo\nSession: manual-clear-safe\nTime: [timestamp]\n\n## Active Workspaces\n### [task-id]\n[full content of context.md read in Step 2]\n\n## Recovery Instructions\nRead workspace/[task-id]/context.md for full task detail.\nContinue from the last documented next step."
}
```

Use the actual context.md content in `workspace_memo`. This is what `session-primer.py` injects after `/clear`.

Then write `$CLAUDEBOOST_HOME/state/clear-pending.json` with the current UTC timestamp:

```json
{"pending": true, "timestamp": "[current UTC ISO timestamp — e.g. 2026-05-12T18:30:00+00:00]"}
```

Replace `[current UTC ISO timestamp]` with the actual current time in ISO format.

This flag is consumed by `session-primer.py` on the first message after `/clear`, which injects the saved workspace context so you resume right where you left off. Do not send any other messages between this step and typing `/clear` — the flag is one-shot.

**Step 5 — Confirm and hand off**

Tell the user:

> Pre-flight complete. Type `/clear` to proceed.
> State is saved to `state/handoff-latest.json` and will be restored on your first message after clearing.
> The next session will restore only **[task-id]** context — not all workspaces.
> Workspace committed to handoff: **[task-id]** — if this is wrong, correct `state/active-workspace.json` before clearing.

If the user says anything other than confirming (asks a question, requests a change):
answer them and do NOT tell them to /clear yet. Only give the go-ahead once they confirm.
