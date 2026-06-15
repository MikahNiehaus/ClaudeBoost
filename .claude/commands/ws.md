---
description: "Show workspace status table for the current project, or switch the active workspace"
allowed-tools: Bash
---

# /ws — Workspace Status

## Arguments: $ARGUMENTS

Run the workspace status script:

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" $ARGUMENTS
```

Display the output to the user exactly as printed.

If `$ARGUMENTS` is non-empty, it is a workspace ID. The script switches the active
workspace and prints `Switched to: <id>`. Relay that confirmation line to the user.

If `$ARGUMENTS` is empty, the script prints a table of workspaces for the current
project — columns: WORKSPACE, DESCRIPTION, EDITED. ✎ marks the most recently edited.
Relay the table as-is; no extra commentary needed unless the user asks.
