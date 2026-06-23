---
description: "Run the ClaudeBoost hook test suite to verify all hook scripts behave correctly"
allowed-tools: Bash
---

# /test-hooks — Run Hook Test Suite

Run the ClaudeBoost hook test harness to verify all hook scripts behave correctly.

## Steps

1. Run the test suite:
   ```bash
   "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/test-hooks.py" -v
   ```

2. Report results:
   - Pass: all tests green — hooks are healthy
   - Fail: show which tests failed and what was expected vs. actual
   - If any hook test fails after a hook change, fix the hook (or update the test if the behavior change was intentional) before proceeding

## When to run

- After any change to a hook script in `scripts/`
- After running `/setup` to verify hook installs didn't break anything
- Before implementing Phase B (mechanical evaluator routing) to confirm green baseline
- As a sanity check after pulling changes from remote


---

## Phase 0: Workspace Detection

**Workspace detection (run before any other action):**

Run `get-active-workspace.py` to get the active workspace for this Claude
instance — matches the blue "WS XXXX" status bar (per-instance, not the
stale shared global file):
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/get-active-workspace.py"
```

Store `project_path` as `PROJECT_PATH` and `workspace_path` as `WORKSPACE_PATH`.
If `PROJECT_PATH` is empty: fall back to current working directory (`pwd`).

**Collision check:** if your context or memory references a different workspace
than what the script returned, print:
`[test-hooks] Conflict: status bar shows <X>, context/memory says <Y>. Which workspace should I use?`
Wait for the user's answer — the user is always the source of truth.

If `WORKSPACE_PATH` is empty: note it and continue.

Include `workspace_path="<WORKSPACE_PATH>"` in ALL agent spawn prompts and `/context` calls.

