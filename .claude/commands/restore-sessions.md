---
description: "Reopen the Claude Code sessions that were open before the last reboot"
allowed-tools: Bash
argument-hint: "[status | dry-run | now | install-task | remove-task]"
---

# /restore-sessions — Reopen what was open before the reboot

## Arguments: $ARGUMENTS (status | dry-run | now | install-task | remove-task)

Default is `status`, because opening a pile of terminal tabs is not something to do by accident.

The ledger at `$CLAUDEBOOST_HOME/state/session-restore.json` is maintained automatically by the `SessionStart` and `SessionEnd` hooks. A reboot never delivers `SessionEnd`, so whatever is still listed is what was open when the machine went down.

The at logon scheduled task runs this for you 90 seconds after login. Use this command to check the ledger, preview what would open, or restore by hand mid day.

---

## Step 1: Parse Arguments

```bash
ACTION="${1:-status}"
case "$ACTION" in
  status|dry-run|now|install-task|remove-task) ;;
  *)
    echo "Usage: /restore-sessions [status|dry-run|now|install-task|remove-task]"
    echo "  status        — show the ledger, live sessions, and what would reopen (default)"
    echo "  dry-run       — print the exact command each tab would run, launch nothing"
    echo "  now           — actually reopen the tabs"
    echo "  install-task  — register the at logon scheduled task"
    echo "  remove-task   — remove the at logon scheduled task"
    exit 0
    ;;
esac
```

---

## Step 2: Run

```bash
SCRIPT="${CLAUDEBOOST_HOME}/scripts/session-restore.py"
case "$ACTION" in
  status)       "${CLAUDEBOOST_PYTHON}" "$SCRIPT" --status ;;
  dry-run)      "${CLAUDEBOOST_PYTHON}" "$SCRIPT" --dry-run ;;
  now)          "${CLAUDEBOOST_PYTHON}" "$SCRIPT" --force ;;
  install-task) "${CLAUDEBOOST_PYTHON}" "$SCRIPT" --install-task ;;
  remove-task)  "${CLAUDEBOOST_PYTHON}" "$SCRIPT" --remove-task ;;
esac
```

**Output interpretation:**

- **status** shows the ledger entries, which of them are live right now, the resolved `claude` path, the terminal it would use, and whether the logon task is registered. An entry marked `live` will be skipped, because a session is already open in that directory.
- **dry-run** prints one block per tab: the directory and the exact `claude --resume <id>` invocation. Read this before running `now` for the first time.
- **now** uses `--force`, so it ignores the once per boot guard. That is the right behaviour for a manual run, since the user asked for it deliberately.
- **install-task** falls back to a Startup folder shim if machine policy refuses `schtasks`. Either outcome is reported explicitly.

If `status` reports `terminal none`, this is not Windows and there is no Windows Terminal to open tabs in. The command prints the resume lines to run by hand instead.

---

## Step 3: Report Honestly

Report what the script actually printed. In particular:

- If the ledger is empty, say so. It fills up as sessions start, so a ledger written before the hooks were installed will be short.
- If entries were skipped, name the reason the script gave (directory gone, already open, written by another machine, stale).
- Never claim tabs opened unless the script printed an `[OK]` line for each one.

---

## Report

**Success (status):**
```
Ledger holds N session(s), M already live. Logon task registered. K would reopen.
```

**Success (now):**
```
Opened K of N session(s) in Windows Terminal.
```

**Nothing to do:**
```
Ledger is empty, or every session in it is already open.
```

**Failed:**
```
session restore error: [the specific message the script printed]
```

---

## What Next

- **The ledger looks wrong**: it is plain JSON at `$CLAUDEBOOST_HOME/state/session-restore.json`. Delete it to start clean, the hooks refill it.
- **The log**: `$CLAUDEBOOST_HOME/state/session-restore.log` records every hook write and every restore.
- **Stop it running at login**: `/restore-sessions remove-task`, or set `CLAUDEBOOST_NO_SESSION_RESTORE_TASK=1` before running setup.
