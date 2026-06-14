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
re-introduce inline `python -c`, bare `$VAR`, or a bare `python`/`python3` token
here — they get blocked or fail to resolve on some platforms. Use the brace-form
interpreter `"${CLAUDEBOOST_PYTHON}"` (setup stores a forward-slash path that
works in Git Bash on Windows too) and `${CLAUDEBOOST_HOME}` for paths.

## Run it

Look at `$ARGUMENTS` above and run **exactly one** of these (always a literal arg,
never `$ARGUMENTS`, so the guard stays happy). The script writes
`state/boost-injection.json` itself:

- `$ARGUMENTS` is `true`:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" true
  ```
- `$ARGUMENTS` is `false`:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" false
  ```
- `$ARGUMENTS` is `verify` or empty:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" verify
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
- If `rag_ready` is `false`: **Auto-repair** — do not just tell the user to run
  `/rag`. Instead, immediately run `setup.py` (which fixes deps, hooks, and state,
  then starts the server), then re-run `boost-run.py verify` once. Only if RAG is
  still not ready after that repair attempt, tell the user:
  "Setup ran but RAG could not start. Check the terminal output above and run
  `/setup` for a detailed diagnosis."
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/setup.py"
  ```
  then re-run:
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/boost-run.py" verify
  ```
- If `missing_hooks` is non-empty: **Auto-repair** — run `setup.py` to re-register
  missing hooks (additive, never duplicates), then report what was fixed.
  ```bash
  "${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/setup.py"
  ```
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
