---
argument-hint: [--purge] [--dry-run]
description: Uninstall ClaudeBoost, reverses /setup (hooks, env, symlinks, MCP, RAG server). --purge also removes pip package, indexes, PATH edits, shared MCPs
allowed-tools: Bash, Read, AskUserQuestion
---

# /uninstall: Remove ClaudeBoost ($ARGUMENTS)

Reverses everything `/setup` installed. The work is done by `scripts/uninstall.py`;
this command runs it safely with a preview and an explicit confirm.

**Default scope (no flags)** removes only ClaudeBoost's own footprint and is fully
reversible by re-running `/setup`:
- CB hooks, env vars, statusLine, and the permission entries setup added, out of `~/.claude/settings.json`
- the `~/.claude` symlinks (`CLAUDE.md`, `commands`) and copied helpers (`ensure-setup.py`, `claudeboost-home.txt`)
- the `rag-server` MCP registration
- stops the running RAG HTTP server and clears its session sentinel

**`--purge`** additionally pip-uninstalls `rag-server`, deletes the ClaudeBoost RAG
index, strips the netcoredbg PATH line from `~/.profile`, and deregisters the shared
MCP servers (`mcp-debugger`, `playwright`). Use it only when you want CB gone for good.

The script never deletes the repo folder, a real `~/.claude/CLAUDE.md` you wrote, any
slash commands you added yourself, or shared ML deps.

## Instructions

1. **Locate home.** Confirm `$CLAUDEBOOST_HOME` is set:
   ```bash
   echo "CLAUDEBOOST_HOME=${CLAUDEBOOST_HOME}"
   ```
   If empty, read `~/.claude/settings.json` with the Read tool and take `env.CLAUDEBOOST_HOME`.
   If that's missing too, ask the user for the repo path.

2. **Preview first (always).** Run a dry-run, forwarding any `--purge` from `$ARGUMENTS`:
   ```bash
   "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/uninstall.py" --dry-run $ARGUMENTS
   ```
   Show the user the plan. Note which `[DRY] would ...` lines are destructive (settings
   edits, symlink removal, MCP deregistration, and under `--purge` the pip uninstall +
   index delete + PATH edit).

3. **If `$ARGUMENTS` contains `--dry-run`, stop here.** The user only wanted a preview.

4. **Confirm before changing anything.** Uninstalling edits the user's *global*
   `~/.claude` config, which affects every project, so this is an irreversible-enough
   action to require a clear YES. Use **AskUserQuestion**:
   > "This removes ClaudeBoost's footprint from your global `~/.claude` config and stops
   > the RAG server (re-runnable via `/setup`). Proceed?"
   > Options: **Yes, footprint only** / **Yes, full purge (--purge)** / **No, cancel**
   (If the user already passed `--purge`, present the purge option as the default.)

5. **Apply.** On confirmation, run the real uninstall with `--yes` so it doesn't prompt
   again, plus `--purge` only if the user chose it:
   ```bash
   "${CLAUDEBOOST_PYTHON:-python3}" "${CLAUDEBOOST_HOME}/scripts/uninstall.py" --yes [--purge]
   ```
   Read the output and summarize what was removed and what was left in place.

6. **Closing note.** Tell the user to **restart any open Claude Code sessions** so they
   drop the removed hooks and slash commands, and that the repo folder is still on disk
   if they want to delete it. Mention `/setup` reinstalls everything if they change their mind.

## Notes

- The default path is reversible: `/setup` reinstalls the full footprint.
- `--purge` is not reversible for free, the RAG index has to be rebuilt with
  `/index-boost` and `/index-project`, and shared MCPs re-registered by `/setup`.
- If the RAG server won't stop, `scripts/restart-rag.py` can be run by hand.
