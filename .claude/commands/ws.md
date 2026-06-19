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

If `$ARGUMENTS` is non-empty, it is a workspace ID or `off`. The script updates the
active workspace for the current project and prints the result. Relay that confirmation
line to the user. (`off` clears the active workspace for this project, showing N/A.)

If `$ARGUMENTS` is empty, the script prints a table of workspaces for the current
project — columns: WORKSPACE, DESCRIPTION, EDITED. ✎ marks the most recently edited.
Relay the table as-is; no extra commentary needed unless the user asks.
