---
argument-hint: [--check | --install]
description: Audit and install all ClaudeBoost hooks. Use --check to just see what is missing, --install to fix everything.
allowed-tools: Read, Write, Edit, Bash, Glob
---

# /better-permissions — Hook Auditor and Installer

Arguments: `[--check | --install]`

Audits all ClaudeBoost hooks in `~/.claude/settings.json` and installs any that are missing.
Default with no arguments: audit + install all missing hooks (same as `--install`).

---

## Phase 1: Load Settings

Read `~/.claude/settings.json`:
```bash
cat "$HOME/.claude/settings.json"
```

If the file does not exist: note that and treat all hooks as missing.

Parse the `hooks` section. You will check for each hook by its sentinel string.

---

## Phase 1.5: Script File Check

Before auditing settings.json, verify each hook script file exists on disk in `$CLAUDEBOOST_HOME/scripts/`.

Check for each of the following files:

```
action-gate.py
agent-spawn-gate.py
auto-clear.py
bash-guard.py
comment-humanness-check.py
compaction-restore.py
consult-gate.py
context-nudge.py
ensure-setup.py
human-voice-guard.py
prompt-rules-injector.py
rag-session-reset.py
research-task-nudge.py
rules-compliance-check.py
session-clear-save.py
session-primer.py
skill-verify-gate.py
speak-stop.py
speak-tts.py
telemetry-hook.py
telemetry-session.py
verify-gate-cmd.py
workspace-boost-gate.py
workspace-primer.py
```

```bash
ls "${CLAUDEBOOST_HOME}/scripts/"
```

Mark each as `✓ EXISTS` or `✗ MISSING`. A hook wired in settings.json that points to a missing script will silently fail — this check catches that before the settings audit.

If any scripts are MISSING, attempt to restore them in this order:

1. Git restore:
   ```bash
   git -C "${CLAUDEBOOST_HOME}" checkout HEAD -- scripts/<file>.py
   ```
2. If the repo is unavailable, run the full installer:
   ```bash
   "${CLAUDEBOOST_HOME}/install.bat"   # Windows
   "${CLAUDEBOOST_HOME}/install.sh"    # macOS/Linux
   ```
3. If neither works, list the missing files and tell the user to re-clone or copy from another machine.

Only proceed to Phase 2 once all script files are confirmed present (or the user accepts the gap).

---

## Phase 2: Audit — Check Each Hook

For each expected hook, search the hooks section for its sentinel string. Mark as INSTALLED or MISSING.

### SessionStart hooks
| Hook | Sentinel |
|------|----------|
| Workflow routing | `Quality-first routing` |
| CONSULT protocol | `CONSULT vs AUTO` |
| RAG HTTP API config | `RAG HTTP API` |
| Compaction restore | `compaction-restore.py` |
| Workspace tier primer | `workspace-primer.py` |
| RAG session reset | `rag-session-reset.py` |
| Telemetry session | `telemetry-session.py` |

### PreToolUse hooks
| Hook | Sentinel |
|------|----------|
| Task RAG gate | `agent-spawn-gate.py` |
| Skill verify gate | `skill-verify-gate.py` |
| Workspace boost gate | `workspace-boost-gate.py` |
| Workspace creation check | `WORKSPACE CREATION CHECK` |
| CONSULT gate | `consult-gate.py` |
| Action form gate | `action-gate.py` |
| Bash guard | `bash-guard.py` |
| Process kill safety | `PROCESS KILL SAFETY` |

### PostToolUse hooks
| Hook | Sentinel |
|------|----------|
| Verify gate | `verify-gate-cmd.py` |
| Context nudge | `context-nudge.py` |
| Comment humanness check | `comment-humanness-check.py` |
| Telemetry action log | `telemetry-hook.py` |

### UserPromptSubmit hooks
| Hook | Sentinel |
|------|----------|
| Auto-setup bootstrap | `ensure-setup.py` |
| RAG session primer | `session-primer.py` |
| Research-task nudge | `research-task-nudge.py` |
| TTS interrupt | `speak-stop.py` |
| Prompt rules injector | `prompt-rules-injector.py` |

### PreCompact hooks
| Hook | Sentinel |
|------|----------|
| Context preservation | `CONTEXT PRESERVATION` |

### Stop hooks
| Hook | Sentinel |
|------|----------|
| Human voice guard | `human-voice-guard.py` |
| Rules compliance check | `rules-compliance-check.py` |
| Auto-clear | `auto-clear.py` |
| TTS speak | `speak-tts.py` |

### SessionEnd hooks
| Hook | Sentinel |
|------|----------|
| Clear handoff save | `session-clear-save.py` |
| Telemetry session end | `telemetry-session.py` |

---

## Phase 3: Report

Print a table of all hooks:

```
Hook Audit Results
──────────────────────────────────────────────────────
  Hook                         Type          Status
  ───────────────────────────────────────────────────
  Quality-first routing        SessionStart  ✓ INSTALLED
  CONSULT protocol             SessionStart  ✓ INSTALLED
  Prompt rules injector        UserPromptS.  ✗ MISSING
  bash-guard.py                PreToolUse    ✓ INSTALLED
  ...

Summary: 22 installed, 1 missing
```

If all hooks are installed and `--check` was passed: print the table and stop.

---

## Phase 4: Install Missing Hooks (skipped if --check)

If any hooks are MISSING (and not in `--check` mode):

Run setup.py to install all missing hooks idempotently:
```bash
"${CLAUDEBOOST_PYTHON}" "${CLAUDEBOOST_HOME}/scripts/setup.py"
```

Setup.py is fully idempotent — it skips hooks that are already installed and adds any that are missing.

After setup.py completes, re-read `~/.claude/settings.json` and re-run the audit (Phase 2) to confirm all hooks are now INSTALLED.

Print a final summary:
```
Hooks installed. Restart Claude Code for changes to take effect.

Before: 22 installed, 1 missing
After:  23 installed, 0 missing
```

If any hooks are still missing after setup.py runs: list them explicitly and tell the user to check that `CLAUDEBOOST_HOME` is set correctly in settings.json.

---

## Notes

- setup.py is idempotent — running it never duplicates hooks that are already installed.
- Changes to hooks take effect on the next Claude Code session (requires restart or /clear).
- To toggle state values (RAG enforcement, CONSULT/AUTO mode, intent override): use `/edit-state`.
- If install.bat or install.sh haven't been run recently, setup.py also installs the RAG server, mcp-debugger, Playwright MCP, and edge-tts.

### Action Gate Form Format

The action form gate (`action-gate.py`) blocks Edit, Write, and MultiEdit until this block appears in the response:

```
[Action]
tool   : Edit | Write | MultiEdit
target : path/to/file
why    : reason for this action
rag    : ClaudeBoost KB: [searched/not needed — why] | Project KB: [searched/not needed — why] | Codebase: [searched/not needed — why] | Workspace KB: [searched/not needed/does not exist — why]
impact : what will change and what it might affect
safe   : yes — why it is safe, or no — what the risk is
```

Every RAG tier requires a real reason. "Not needed" is fine but must explain why. "Does not exist" is valid for Workspace KB when no workspace is active. Bare "n/a" is not accepted.
