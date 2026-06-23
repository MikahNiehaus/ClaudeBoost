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
