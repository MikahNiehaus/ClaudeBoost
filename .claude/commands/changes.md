# Show Interactive Change Explorer

Display all code changes with AI-generated explanations in an interactive terminal tab.

## Step 1: Detect Changes

Run these commands to find what changed:
```bash
git diff --stat 2>/dev/null
git diff --staged --stat 2>/dev/null
```

If both are empty, fall back to last commit:
```bash
git diff HEAD~1 --stat 2>/dev/null
```

If still nothing, tell the user "No changes to show" and STOP. Do not open a tab.

Otherwise, report what you found: "Found N files with changes. Generating explanations..."

**Size gate**: If more than 30 files changed, ask the user if they want to proceed or narrow the scope.

## Step 2: Get Full Diff

Capture the unified diff:
```bash
git diff 2>/dev/null
git diff --staged 2>/dev/null
```
Or if using fallback: `git diff HEAD~1 2>/dev/null`

## Step 3: Agent Attribution

Scan recent commits for agent names:
```bash
git log --oneline -20 2>/dev/null
```

Look for patterns like `workflow-agent`, `debug-agent`, etc. in commit messages. Also check if any `workspace/*/context.md` exists and read agent contributions from it. Default attribution is "orchestrator" for anything unattributed.

## Step 4: Generate Explanations

For each changed file and each diff hunk, generate a JSON object following this exact schema:

```json
{
  "generated_at": "<ISO timestamp>",
  "project": "<current directory name>",
  "summary": {
    "files_changed": <count>,
    "lines_added": <count>,
    "lines_removed": <count>,
    "agents": ["<agent-name>", ...]
  },
  "files": [
    {
      "path": "<relative file path>",
      "status": "modified|added|deleted",
      "agent": "<agent-name or orchestrator>",
      "summary": "<1 sentence file-level summary>",
      "hunks": [
        {
          "header": "<@@ line range @@>",
          "old_code": "<removed lines or empty>",
          "new_code": "<added lines or empty>",
          "explanation": "<1-2 sentence explanation of what and why>"
        }
      ]
    }
  ]
}
```

**Writing style for explanations**: Concise, non-formal, professional. No dashes. Each explanation is 1 to 2 sentences explaining what the change does and why it matters.

**For better explanations**: Read a few lines of surrounding context in each changed file (use Read tool) so you understand the purpose, not just the diff.

## Step 5: Save Outputs

Determine save location:
- If any `workspace/*/` directory exists (check most recently modified), save there
- Otherwise, create and use `$TEMP/claudeboost/`

Write two files:
1. `changes.json` at the save location (for the TUI to read)
2. `changes.md` at the save location (human-readable documentation)

The markdown file format:
```
# Changes — <date>

## Summary
<N> files changed | +<M> / -<K> lines | Agents: <list>

## <path/to/file.py> (<status>) — <agent>
<file summary>

### <hunk header>
**Added:**
<new code>

**Explanation:** <explanation text>
```

## Step 6: Launch TUI

Open the interactive viewer in a new terminal tab:
```bash
wt.exe -w last new-tab --title "CHANGES" python "C:/Users/grayw/OneDrive/prj/ClaudeBoost/scripts/changes-viewer.py" "<save-path>/changes.json"
```

**NEVER use `powershell Start-Process` or `cmd start`** — those open separate windows.

## Step 7: Report

Tell the user:
- How many files and explanations were generated
- Where the documentation was saved
- That the TUI is open in the adjacent tab
