---
description: Save workspace state, then launch a new terminal with claude ready to go — no manual steps needed
allowed-tools: Bash, Read, Edit, Write
---

# /clear-safe — Safe context handoff

## Step 1 — Update context.md

Read the active workspace's context.md. You know what happened this session — write it in.
Add or update these sections (preserve everything else):

- **Status**: what was accomplished this session, 1-2 sentences
- **Next step**: the single most concrete next action
- **Key decisions**: any technical choices made this session
- **Last updated**: today's date (YYYY-MM-DD)

To find the active workspace: read `$CLAUDEBOOST_HOME/state/active-workspace.json` (field: `workspace`),
then resolve the path from `$CLAUDEBOOST_HOME/state/workspaces.json` or look in `./workspace/[id]/`.

If there is no active workspace, skip straight to Step 2 with workspace-id="" and workspace-path="none".

## Step 2 — Run the launch script

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/clear-safe-launch.py" \
  --workspace-id "[workspace id from Step 1]" \
  --workspace-path "[absolute path to the workspace folder]" \
  --next-step "[exact next step text you wrote in context.md]"
```

## Step 3 — Tell the user

> Done. New tab opening with context loaded. This session is closing now.
