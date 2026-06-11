---
description: "<true|false|verify>  true: always-on rules only  |  false: off  |  verify: full RAG activation"
allowed-tools: Bash, Read, Glob
---

# ClaudeBoost Activation

## Arguments: $ARGUMENTS

The whole flow runs in one helper script — `scripts/boost-run.py`. It does the
banner, privacy check, RAG server start + health, dimension-mismatch heal,
context priming, self-index, hooks/rules/mode checks, mcp-debugger check, and
workspace discovery, then prints a report ending in a `=== BOOST_SUMMARY ===`
JSON line.

**Why one script:** `bash-guard.py` blocks bare `$VAR` expansion and multiline
`python -c`, and macOS has no bare `python`. The script avoids all three. Do NOT
re-introduce inline `python -c`, `$VAR`, or bare `python` here — they get blocked.

## Run it

Look at `$ARGUMENTS` above and run **exactly one** of these (always a literal arg,
never `$ARGUMENTS`, so the guard stays happy). The script writes
`state/boost-injection.json` itself:

- `$ARGUMENTS` is `true`:
  ```bash
  python3 "${CLAUDEBOOST_HOME}/scripts/boost-run.py" true
  ```
- `$ARGUMENTS` is `false`:
  ```bash
  python3 "${CLAUDEBOOST_HOME}/scripts/boost-run.py" false
  ```
- `$ARGUMENTS` is `verify` or empty:
  ```bash
  python3 "${CLAUDEBOOST_HOME}/scripts/boost-run.py" verify
  ```

(`${CLAUDEBOOST_HOME}` brace form passes the guard; the env var is set by
`install.sh`. If it's somehow unset, the script falls back to its own location.)

## After it runs

**true / false:** relay the one-line message the script printed, then stop.

**verify:** present the report from the script's output. Then read the
`=== BOOST_SUMMARY ===` JSON line and act on it:

- If `active_workspaces` has **exactly one** entry, read
  `<project_cwd>/workspace/<that-id>/context.md` and summarize where it left off
  ("Resuming task [id] — last status was [X]").
- If `rag_ready` is `false`: tell the user "RAG did not come up. Run `/rag`, then
  re-run `/boost`." Do not proceed with degraded context.
- If `healed_scopes` is non-empty: note that those collections were rebuilt to
  match the embedding model (a model swap had left them unqueryable).

### Report format — include these sections

**Systems Status**
- RAG: ready/failed — HTTP port 8612 (model, dimension, knowledge + agents chunks/files)
- Dimension heal: which scopes were rebuilt, or "none needed"
- Self-index: files, chunks, graph edges resolved
- Memories: chunks indexed (or "empty / not indexed")
- mcp-debugger: connected / not registered / not checked
- Hooks: all 6 present, or which are missing
- Rules: CLAUDE.md loaded/missing

**Active Workspaces**
- List discovered workspaces; if resuming one, say so. If none: "No active workspaces."

**Session Directives**
- "RAG is live on HTTP port 8612. I'll POST /context first when spawning agents, and POST /search when I need knowledge."

**Collaborative Mode**
- CONSULT (default): "I'll research, propose via architect-agent (Opus), and ask before architectural decisions. `/auto` to bypass."
- AUTO: "Autonomous mode — I'll proceed without consulting. `/consult` to restore."

**Ready**
- All passed: "ClaudeBoost is live. Status line shows RAG ● when healthy."
- RAG warming: "RAG ○ — model loading, ready in ~60s."
- Anything failed: explain what and how to fix it.
