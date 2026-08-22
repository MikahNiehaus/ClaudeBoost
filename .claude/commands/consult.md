---
argument-hint: (no arguments)
description: Enter CONSULT mode — Claude will research + propose + ask before architectural decisions (default)
allowed-tools: Read, Write, Edit, Bash
---

# Enter CONSULT Mode

Return ClaudeBoost to its default **CONSULT** mode. For any architectural decision, Claude will:

1. `POST /search` + read 2–3 relevant project files
2. Spawn `architect-agent` (Opus) with `PROPOSAL_ONLY` and file:line citations
3. Present 2–3 options via `AskUserQuestion` — you pick, edit, or add
4. Log your approval and implement

Consultation is **additive, not gatekeeping** — RAG-required standards (security, logging, validation) are applied automatically. Your job is to add constraints on top (size caps, charset allowlists, rate limits, etc.).

## Instructions

1. **Read current mode**: `Read $CLAUDEBOOST_HOME/state/claudeboost-mode.json`

2. **Write updated mode**:
   ```json
   {
     "mode": "CONSULT",
     "setAt": "<current ISO 8601 timestamp>",
     "setBy": "user /consult",
     "reason": "returning to default collaborative mode"
   }
   ```

3. **Confirm to user**:
   > CONSULT mode active. I will research, propose, and ask before architectural decisions.
   >
   > **Triggers**: new endpoints, new DB tables, new dependencies, new middleware, auth/validation/error/logging strategies, new modules, new config surfaces, new concurrency models.
   >
   > **Not triggers**: typos, single-line fixes, tests, docs, value-only config tweaks, renames within one file, edits under workspace/ state/ .claude/ plans/ docs/.
   >
   > Use `/auto` to bypass consultation for prototyping or trivial work.
