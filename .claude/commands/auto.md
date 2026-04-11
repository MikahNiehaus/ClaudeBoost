---
argument-hint: [reason]
description: Enter AUTO mode — Claude acts autonomously without consulting on architecture
allowed-tools: Read, Write, Edit, Bash
---

# Enter AUTO Mode: $ARGUMENTS

Switch ClaudeBoost out of CONSULT mode. Claude will make architectural decisions autonomously until you run `/consult`.

## Instructions

1. **Read current mode**: `Read $CLAUDEBOOST_HOME/state/claudeboost-mode.json`

2. **Write updated mode**:
   ```json
   {
     "mode": "AUTO",
     "setAt": "<current ISO 8601 timestamp>",
     "setBy": "user /auto",
     "reason": "$ARGUMENTS"
   }
   ```
   If `$ARGUMENTS` is empty, use `"user requested autonomous mode"`.

3. **Confirm to user**:
   > AUTO mode active. I will proceed autonomously on architectural decisions (new endpoints, tables, deps, middleware, etc.) and still cite patterns I follow.
   >
   > **Reminder**: rework from wrong architecture costs more than a 30-second consultation. Use AUTO for exploration, prototypes, and trivial work. Run `/consult` to re-enable consultation.
