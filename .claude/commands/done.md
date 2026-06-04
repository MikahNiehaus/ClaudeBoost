---
description: Verify work is clean and push to remote
allowed-tools: Bash(git status:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(git push:*)
argument-hint: [--message "optional commit message"]
---

# Done — Push Work to Remote

Verify your work is ready, then push to the remote branch.

Arguments: $ARGUMENTS

## Phase 0: Load RAG Context (MANDATORY FIRST ACTION)

Call `POST http://127.0.0.1:8612/context with agent="workflow-agent", task_description="final quality gate before pushing work", max_tokens=3000`.

If `POST http://127.0.0.1:8612/context` fails: stop and tell the user "RAG is not connected. Run /rag before using this skill."

---

## Pre-flight Checks

```bash
git status
git log --oneline origin/main..HEAD 2>/dev/null || git log --oneline -5
```

**Must pass before pushing:**
- Working tree is clean (no uncommitted changes)
- At least 1 commit ahead of the base branch

If there are uncommitted changes, commit them first:
```bash
git add <files>
git commit -m "<type>: <description>"
```

---

## Push

```bash
git push
```

If the branch has no upstream yet:
```bash
git push -u origin HEAD
```

Report the result. If the push fails, show the error and stop — do not force-push.
