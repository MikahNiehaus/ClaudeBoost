---
argument-hint: [on | off | status | --threshold N]
description: Toggle Low Token Mode — auto-opens a new terminal and closes the current one when context fills up
allowed-tools: Bash
---

# /low-token — Low Token Mode Toggle

Arguments: `[on | off | status] [--threshold N]`

Toggles Low Token Mode for this machine. State is stored in `state/low-token-mode.json`
(gitignored — per-machine, not shared via git).

**What it does when ON:**
- Status bar shows `LT ●` colored by context pressure (green/yellow/red vs threshold)
- When context fills to compaction point, a new Windows Terminal tab opens in the same directory
- The current session closes after the turn ends
- The new session starts fresh and picks up `handoff-latest.json` via compaction-restore

**When OFF:** no behavior change from normal ClaudeBoost operation.

---

## Phase 1: Run the toggle

```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/low-token-toggle.py" $ARGUMENTS
```

Report the output verbatim.

---

## Phase 2: If turning ON — confirm what's active

After enabling, tell the user:

```
Low Token Mode is ON (threshold: [N]%)

What changes:
  Status bar: shows LT ● (green below [N]%, yellow to [N+10]%, red above)
  At compaction: new terminal opens in [current dir], this session closes after the turn
  New session: picks up handoff state automatically via compaction-restore

To turn off:  /low-token off
To adjust:    /low-token on --threshold 60
```

## Phase 2b: If turning OFF — confirm

```
Low Token Mode is OFF. Normal compaction behavior restored.
```

## Notes

- The threshold controls the status bar color bands only — it does NOT change when
  compaction fires. That is controlled by CLAUDE_AUTOCOMPACT_PCT_OVERRIDE in settings.json
  (default ~83%). Use `/update-config` to adjust that separately.
- On non-Windows machines, the signal is written but no new terminal launches automatically.
  The session closes and the user opens a new one manually.
- State is machine-local. Running `/low-token on` on one machine does not affect others.
