---
description: Verify work is clean, then hand the git commands to the user to run
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git diff:*), Bash(git branch --show-current), Bash(git rev-parse:*), Bash(echo:*), Bash(clip.exe:*)
argument-hint: [--message "optional commit message"]
---

# Done

Verify the work is ready, then hand the user the git commands to run themselves.

Arguments: $ARGUMENTS

**This command never runs a git command that writes.** Staging, committing and
pushing are the user's to run. Every write command in this file is put on the
clipboard and described, not executed. `git add`, `git commit` and `git push`
are denied by the permission config, so attempting one fails rather than
prompting.

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

**0a — Detect project path (before loading context):**

1. Run `"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"` to get the active workspace ID for this Claude instance (same source as the blue WS indicator — per-instance, not shared). Output is JSON with `workspace_id`, `workspace_path`, `project_path`. Fall back to current working directory if no workspace is active.

Set `PROJECT_PATH` to the detected value.

Call `POST http://127.0.0.1:8613/search with {"query":"final quality gate before pushing work","sources":["project:<PROJECT_PATH>"],"mode":"both","limit":8}`.

If `POST http://127.0.0.1:8613/search` fails: stop and tell the user "RAG is not connected. Run /rag before using this skill."

---

## Checks Before Handoff

```bash
git status
git log --oneline origin/main..HEAD 2>/dev/null || git log --oneline -5
git branch --show-current
```

Read the output and report which of these hold:

- Working tree is clean, no uncommitted changes
- At least 1 commit ahead of the base branch

---

## Handoff

Work out which commands the user needs from the check output above, then hand
them over one at a time. Do not batch several writes into one clipboard entry:
the user approves each one on its own.

For each command:

1. Put the exact text on the clipboard:
   ```bash
   echo '<command>' | clip.exe
   ```
2. Say in one or two sentences what it does and whether it is reversible.
3. Ask the user to run it by typing `! ` and pasting.

Then wait. Do not move to the next command until the user reports the result.

### Uncommitted changes

Name the files first so the user is not pasting a wildcard blind.

| Command | What it does | Reversible |
|---|---|---|
| `git add <files>` | Stages those files for the next commit | Yes, `git restore --staged <files>` |
| `git commit -m "<type>: <description>"` | Records the staged files as a commit on the current branch | Yes while unpushed, `git reset --soft HEAD~1` |

### Push

| Command | What it does | Reversible |
|---|---|---|
| `git push` | Sends the local commits on this branch to the remote | Not on your own. Undoing a push rewrites published history |
| `git push -u origin HEAD` | Same, and sets this branch to track the remote branch. Use when the branch has no upstream yet | Same |

If the user reports the push failed, show the error and stop. Do not hand over
a force push to work around it.
