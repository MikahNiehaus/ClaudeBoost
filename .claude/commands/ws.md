---
description: "Show workspace status table for the current project, or switch the active workspace"
allowed-tools: Bash
---

# /ws — Workspace Status

## Arguments: $ARGUMENTS

Before running, interpret the user's intent:
- If `$ARGUMENTS` is empty or "list" → list mode (no arg to script)
- If `$ARGUMENTS` is `off` → pass `off` to clear the active workspace
- If `$ARGUMENTS` looks like a workspace ID or partial name (including natural language like "the dispute one") → extract the key search term and pass that single word/phrase as the argument

For natural language like "set ws for the dispute one" or "switch to disputes", extract the meaningful identifier ("disputes") and pass only that to the script.

Run the workspace status script:

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/workspace-status.py" <extracted-id-or-empty>
```

Display the output to the user exactly as printed.

**Switching:** The script accepts exact workspace IDs, partial names (fuzzy match), or
local folder names from `./workspace/` in the current directory. If the match is
ambiguous, it lists what matched. Pass `off` to clear the active workspace.

**Listing:** When no argument is given, shows all workspaces for the current project,
including local folders found in `./workspace/` that aren't in the global registry
(marked with `(local)`). ✎ marks the most recently edited.
