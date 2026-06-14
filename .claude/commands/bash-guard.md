---
argument-hint: [on|off|status]
description: Toggle bash-guard.py, disable or re-enable the Bash safety guard that blocks prompt-triggering commands
allowed-tools: Bash, Read
---

# /bash-guard: Bash Guard Control ($ARGUMENTS)

`bash-guard.py` is the PreToolUse hook on Bash. It blocks command shapes that trip
Claude Code's built-in permission prompts (compound `cd && ...`, multiline `python -c`,
`cat` heredocs, bare `$VAR` expansion, external `curl`/`ssh`/`nc`, Co-Authored-By
trailers). Disable it when those blocks get in your way; re-enable it to get the
safety net back.

Under the hood the guard reads `CLAUDEBOOST_BASH_GUARD` from the `env` block of
`~/.claude/settings.json` (bash-guard.py treats `off`/`0`/`false`/`disabled`/`no` as off).
This command flips that key via `scripts/toggle-bash-guard.py`, which edits only that
one entry and leaves the rest of settings.json untouched.

## Instructions

Parse `$ARGUMENTS` and run the toggle script. Default to `status` when empty.

- **Empty or `status`**, report the current state:
  ```bash
  "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/toggle-bash-guard.py" status
  ```

- **`off`** (or `disable`), turn the guard off:
  ```bash
  "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/toggle-bash-guard.py" off
  ```
  Then warn briefly:
  > bash-guard off. Commands that normally trigger Claude Code permission prompts
  > (compound `cd`, multiline `python -c`, heredocs, external `curl`/`ssh`) will now
  > go through unguarded. Re-enable with `/bash-guard on`.

- **`on`** (or `enable`), turn the guard back on:
  ```bash
  "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/toggle-bash-guard.py" on
  ```
  Confirm:
  > bash-guard on. Safety guard active again.

## Notes

- The change is written to `~/.claude/settings.json`. It applies to subsequent Bash
  calls; if a guarded command still blocks right after toggling off, start a fresh
  Claude Code session so the new env value is picked up.
- This only affects `bash-guard.py`. The other PreToolUse guards (`git-guard.py`,
  `consult-gate.py`, `agent-spawn-gate.py`) are unaffected.
- `/setup` does not turn the guard back on by itself, but `/uninstall` clears the
  `CLAUDEBOOST_BASH_GUARD` key along with the rest of ClaudeBoost's env.
