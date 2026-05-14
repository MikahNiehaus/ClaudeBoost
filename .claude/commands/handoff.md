---
description: Hand off to fresh session via Gas Town (gt handoff) — for tmux/beads session cycling
allowed-tools: Bash(gt handoff:*)
argument-hint: [message]
---

# /handoff — Gas Town Session Cycling

**This skill requires Gas Town (`gt`) running in a tmux session.**
If you are NOT in tmux, this will fail. For post-clear context restore,
use `/restore` instead — it reads `state/handoff-latest.json` directly.

---

User's handoff message (if any): $ARGUMENTS

Execute these steps in order:

1. Check if running in tmux — if `gt handoff` returns "not running in tmux",
   stop immediately and tell the user:
   > Not in tmux — `gt handoff` cannot cycle sessions here.
   > Use `/restore` to restore saved context from the last `/clear-safe` run.

2. If user provided a message, run the handoff command with a subject and message.
   Example: `gt handoff -s "HANDOFF: Session cycling" -m "USER_MESSAGE_HERE"`

3. If no message was provided, run the handoff command:
   `gt handoff`

Note: The new session will auto-prime via the SessionStart hook and find your handoff mail.
End watch. A new session takes over, picking up any molecule on the hook.
