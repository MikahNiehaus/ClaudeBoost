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
- When context fills to compaction point, the full sequence fires automatically:
  1. `compaction-save.py` (PreCompact) writes the handoff state to `state/handoff-latest.json`
  2. `lt-precompact.py` (PreCompact) opens a new Windows Terminal tab in the current directory and auto-submits `continue` as the first message — no user typing needed
  3. `auto-clear.py` (Stop) kills this session after the turn ends
  4. The new session's UserPromptSubmit hook reads `clear-pending.json`, loads the handoff, and injects workspace context + task details before Claude's first response
- Claude in the new session immediately continues the task — the user sees no break in the work

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
  At compaction:  handoff saved → new terminal opens in [current dir] with claude running → "continue" auto-submitted → this session killed
  New session:    handoff context injects automatically → Claude picks up where it left off — no user input needed

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
- The three hooks that make this work must all be wired in settings.json:
  - `lt-precompact.py` → PreCompact (opens new terminal, writes clear-pending.json)
  - `auto-clear.py` → Stop (kills the old session after the turn)
  - `session-primer.py` → UserPromptSubmit (injects handoff context in the new session)
  Run `/better-permissions` if the automatic handoff isn't working — one of these hooks is probably missing.
- On non-Windows machines, the signal is written but no new terminal launches automatically.
  The session closes and the user opens a new one manually.
- State is machine-local. Running `/low-token on` on one machine does not affect others.
