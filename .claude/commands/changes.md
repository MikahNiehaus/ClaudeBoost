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

1. Read the template: `C:/Users/grayw/OneDrive/prj/ClaudeBoost/scripts/changes-template.json`
2. Copy it to `workspace/[task-id]/changes/changes.json`
3. Fill in all fields following the `_field_guide` instructions in the template
4. Delete the `_instructions` and `_field_guide` fields from the filled copy

**Writing style for explanations**: Concise, non-formal, professional. No dashes. Each explanation is 1 to 2 sentences explaining what the change does and why it matters.

**For better explanations**: Read a few lines of surrounding context in each changed file (use Read tool) so you understand the purpose, not just the diff.

## Step 5: Save Outputs

Save location is ALWAYS the project's workspace:
1. If a `workspace/[task-id]/` directory exists for the current task, save to `workspace/[task-id]/changes/`
2. If no workspace exists yet, create `workspace/changes-YYYY-MM-DD/changes/`
3. NEVER use `$TEMP` — changes documentation belongs with the project

Write two files to `workspace/[task-id]/changes/`:
1. `changes.json` (for the TUI viewer to read)
2. `changes.md` (human-readable documentation that persists in the workspace)

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
wt.exe -w last new-tab --title "CHANGES" python "C:/Users/grayw/OneDrive/prj/ClaudeBoost/scripts/changes-viewer.py" "workspace/[task-id]/changes/changes.json"
```

**NEVER use `powershell Start-Process` or `cmd start`** — those open separate windows.

## Step 7: Report

Tell the user:
- How many files and explanations were generated
- Where the documentation was saved
- That the TUI is open in the adjacent tab
