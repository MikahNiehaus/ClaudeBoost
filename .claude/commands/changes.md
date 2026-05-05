---
argument-hint: [scope — e.g. "last 3 commits", "staged", "src/", "HEAD~5..HEAD"]
description: Show Interactive Change Explorer
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Show Interactive Change Explorer

Display code changes with AI-generated explanations in an interactive terminal tab.

Scope: **$ARGUMENTS**

## Step 1: Resolve Scope

If `$ARGUMENTS` is non-empty, interpret it to build the git diff command(s). Use natural language understanding — these are guidelines, not rigid patterns:

| User says | Diff stat command | Diff command |
|-----------|-------------------|--------------|
| `last N commits` / `N commits` | `git diff HEAD~N --stat` | `git diff HEAD~N` |
| `staged` | `git diff --staged --stat` | `git diff --staged` |
| `unstaged` | `git diff --stat` | `git diff` |
| A commit range like `A..B` | `git diff A..B --stat` | `git diff A..B` |
| A branch name | `git diff <branch> --stat` | `git diff <branch>` |
| A file or directory path | Auto-detect diff + append `-- <path>` | Auto-detect diff + append `-- <path>` |
| Anything else | Interpret intent, pick the closest git diff invocation |

**If `$ARGUMENTS` is empty** (no scope provided), auto-detect:
```bash
git diff --stat 2>/dev/null
git diff --staged --stat 2>/dev/null
```
If both are empty, fall back to last commit:
```bash
git diff HEAD~1 --stat 2>/dev/null
```

Run the resolved stat command. If nothing comes back, tell the user "No changes to show" and STOP.

Otherwise, report what you found: "Found N files with changes. Generating explanations..."

**Size gate**: If more than 30 files changed, ask the user if they want to proceed or narrow the scope.

## Step 2: Get Full Diff

Run the resolved diff command (without `--stat`) to capture the unified diff. This must match the same scope from Step 1.

## Step 3: Agent Attribution

Scan recent commits for agent names:
```bash
git log --oneline -20 2>/dev/null
```

Look for patterns like `workflow-agent`, `debug-agent`, etc. in commit messages. Also check if any `workspace/*/context.md` exists and read agent contributions from it. Default attribution is "orchestrator" for anything unattributed.

## Step 4: Generate Explanations

1. Read the template: `$CLAUDEBOOST_HOME/scripts/changes-template.json`
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

Ensure the `textual` dependency is installed, then open the interactive viewer in a new terminal tab:
```bash
python -c "import textual" 2>/dev/null || pip install textual
wt.exe -w 0 new-tab --title "CHANGES" python "$CLAUDEBOOST_HOME/scripts/changes-viewer.py" "workspace/[task-id]/changes/changes.json"
```

**NEVER use `powershell Start-Process` or `cmd start`** — those open separate windows.

**Note**: `wt.exe -w 0` targets the currently focused Windows Terminal window. If the user has multiple WT windows and focuses a different one, the tab may land there. This is a known WT limitation — no flag reliably targets the originating window.

## Step 7: Report

Tell the user:
- How many files and explanations were generated
- Where the documentation was saved
- That the TUI is open in the adjacent tab
- That they can ask questions about code in the chat box at the bottom of the diff view

## Step 8: Chat Monitor

The TUI has a chat input box. When the user types a question, it gets written to `$TEMP/claudeboost/changes_chat.json`. The TUI auto-polls for answers every 3 seconds.

**How to monitor**: Use the `Read` tool to check `$TEMP/claudeboost/changes_chat.json` periodically (when user interaction pauses or when they mention asking a question in the viewer). When a question with an empty `answer` field is found:
1. Read the `question`, `context_file`, and `context_code` fields
2. Generate a concise answer about that code
3. Write the answer back using the Write tool — update the `answer` and `answered_at` fields
4. The TUI picks up the answer automatically and displays it inline

Chat file format:
```json
{
  "question": "What does this lock do?",
  "context_file": "src/services/sync_orchestrator.py",
  "context_code": "self._sync_lock = threading.Lock()",
  "asked_at": "2026-04-05T02:30:00",
  "answer": "",
  "answered_at": ""
}
```
