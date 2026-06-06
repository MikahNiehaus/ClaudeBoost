"""ClaudeBoost portable setup — cross-platform (Windows, macOS, Linux).

Run once after cloning, then any time after `git pull`:
    python scripts/setup.py

Idempotent. Replaces the old setup.ps1 as the single source of truth.
On Windows, install.bat and setup.ps1 both delegate here.

What it does:
  1. Preflight: python / pip / claude / git on PATH.
  2. Resolves CLAUDEBOOST_HOME from the script location.
  3. Merges rag-server into ~/.claude/mcp.json and ~/.claude.json (preserves siblings).
  4. Writes CLAUDEBOOST_HOME env + statusLine into ~/.claude/settings.json.
  5. Mirrors slash commands from repo .claude/commands/ to ~/.claude/commands/.
  6. Seeds state/ (CONSULT mode default, session-approvals, speak-state).
  7. Cleans stale hooks then installs/upgrades 13 hook entries idempotently.
  8. Copies ensure-setup.py into ~/.claude/ so its path is stable across machines.
  9. Installs rag-server in editable mode, upgrades sentence-transformers stack,
     drops incompatible torchvision if present, runs health check.
 10. Installs edge-tts (Windows + macOS only — Linux not supported for speak).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Colors — ANSI codes work everywhere modern (Windows Terminal, macOS, Linux).
# Falling back to plain on dumb terminals keeps log files readable.
# ---------------------------------------------------------------------------
_USE_COLOR = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
_C = {
    "cyan":   "\033[36m" if _USE_COLOR else "",
    "green":  "\033[32m" if _USE_COLOR else "",
    "yellow": "\033[33m" if _USE_COLOR else "",
    "red":    "\033[31m" if _USE_COLOR else "",
    "reset":  "\033[0m"  if _USE_COLOR else "",
}

def _say(msg: str, color: str = "") -> None:
    print(f"{_C.get(color, '')}{msg}{_C['reset']}")

def _ok(msg: str)   -> None: _say(f"[OK] {msg}", "green")
def _warn(msg: str) -> None: _say(f"[WARN] {msg}", "yellow")
def _err(msg: str)  -> None: _say(f"[ERROR] {msg}", "red")
def _skip(msg: str) -> None: _say(f"[SKIP] {msg}", "yellow")
def _info(msg: str) -> None: _say(msg, "cyan")


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BOOST_HOME = Path(__file__).resolve().parent.parent
# POSIX path is what gets written into settings.json so hook commands work
# under sh on every OS (Claude Code uses sh for the statusLine command on
# Windows too, via Git Bash / WSL-style path resolution).
BOOST_HOME_POSIX = BOOST_HOME.as_posix()
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
MCP_PATH = CLAUDE_DIR / "mcp.json"
CLAUDE_JSON_PATH = Path.home() / ".claude.json"

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


# ---------------------------------------------------------------------------
# JSON helpers — UTF-8 without BOM. PowerShell's default UTF8 adds a BOM that
# breaks Claude Code's JSON parser, which is why setup.ps1 went out of its
# way to use .NET UTF8Encoding(false). Python's default is BOM-less, so we
# can just write normally.
# ---------------------------------------------------------------------------
def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        raise

def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Preflight: check required tools on PATH.
# ---------------------------------------------------------------------------
def preflight() -> bool:
    _info("Running preflight checks...")
    ok = True
    # python may be `python3` on macOS/Linux — accept either.
    # pip is checked via `python -m pip` instead of a bare `pip` binary,
    # since macOS commonly ships Python without exposing `pip` on PATH.
    requirements = [
        ("python", "Python 3.9+", True, lambda: bool(shutil.which("python") or shutil.which("python3"))),
        ("pip",    "pip",          True, lambda: subprocess.run([sys.executable, "-m", "pip", "--version"],
                                                                capture_output=True).returncode == 0),
        ("claude", "Claude Code CLI", True, lambda: bool(shutil.which("claude"))),
        ("git",    "Git",          False, lambda: bool(shutil.which("git"))),
    ]
    for cmd, label, required, check in requirements:
        if check():
            _ok(label)
        elif required:
            _err(f"{label} not found — install before re-running setup.")
            ok = False
        else:
            _warn(f"{label} not found — some features may not work.")
    return ok


# ---------------------------------------------------------------------------
# MCP cleanup: remove rag-server from mcp.json if it was registered by an
# older version of setup. The RAG server is now a standalone HTTP daemon on
# port 8612 — no MCP registration needed or wanted.
# ---------------------------------------------------------------------------
def update_mcp_configs() -> None:
    # ~/.claude/mcp.json — remove rag-server if present from old installs
    mcp = read_json(MCP_PATH, {"mcpServers": {}})
    mcp.setdefault("mcpServers", {})
    if "rag-server" in mcp["mcpServers"]:
        del mcp["mcpServers"]["rag-server"]
        write_json(MCP_PATH, mcp)
        _ok("mcp.json - removed old rag-server stdio entry (RAG uses HTTP now)")
    else:
        _skip("mcp.json - rag-server not present, nothing to clean up")

    # ~/.claude.json — remove rag-server if present
    if CLAUDE_JSON_PATH.exists():
        try:
            cj = read_json(CLAUDE_JSON_PATH, {})
        except json.JSONDecodeError:
            _warn(f".claude.json is malformed; skipping cleanup (path: {CLAUDE_JSON_PATH})")
            return
        if "rag-server" in cj.get("mcpServers", {}):
            del cj["mcpServers"]["rag-server"]
            write_json(CLAUDE_JSON_PATH, cj)
            _ok(".claude.json - removed old rag-server entry")
        else:
            _skip(".claude.json - rag-server not present, nothing to clean up")
    else:
        _skip(".claude.json - not found, skipping")


# ---------------------------------------------------------------------------
# State directory — CONSULT mode default, empty session approvals, TTS off.
# ---------------------------------------------------------------------------
def seed_state() -> None:
    state_dir = BOOST_HOME / "state"
    state_dir.mkdir(exist_ok=True)

    mode_path = state_dir / "claudeboost-mode.json"
    now = datetime.now(timezone.utc).isoformat()
    if not mode_path.exists():
        write_json(mode_path, {
            "mode": "CONSULT", "setAt": now,
            "setBy": "setup", "reason": "ClaudeBoost default",
        })
        _ok("state/claudeboost-mode.json - seeded CONSULT default")
    else:
        try:
            current_mode = read_json(mode_path, {}).get("mode", "UNKNOWN")
        except Exception:
            current_mode = "UNKNOWN"
        if current_mode == "CONSULT":
            _ok("state/claudeboost-mode.json - already CONSULT")
        else:
            # /setup always enforces the default (same as the PowerShell version).
            write_json(mode_path, {
                "mode": "CONSULT", "setAt": now, "setBy": "setup",
                "reason": f"reset to default by /setup (was: {current_mode})",
            })
            _ok(f"state/claudeboost-mode.json - reset to CONSULT (was: {current_mode})")

    approvals_path = state_dir / "session-approvals.json"
    if not approvals_path.exists():
        write_json(approvals_path, {"sessionId": "", "approvals": []})
        _ok("state/session-approvals.json - seeded empty")
    else:
        _skip("state/session-approvals.json - preserving existing session data")

    speak_path = state_dir / "speak-state.json"
    if not speak_path.exists():
        write_json(speak_path, {
            "enabled": False,
            "voice": "en-US-AndrewNeural",
            "setAt": now,
            "setBy": "default",
        })
        _ok("state/speak-state.json - seeded TTS disabled default")
    else:
        _skip("state/speak-state.json - preserving existing setting")


# ---------------------------------------------------------------------------
# Slash commands — repo .claude/commands/*.md is the source of truth.
# We mirror to ~/.claude/commands/ so they load in every project, not just
# when cwd is inside ClaudeBoost.
# ---------------------------------------------------------------------------
def sync_slash_commands() -> None:
    src = BOOST_HOME / ".claude" / "commands"
    dst = CLAUDE_DIR / "commands"
    if not src.is_dir():
        _skip(f"slash commands - source dir not found: {src}")
        return
    # If dst is a Windows junction or POSIX symlink to the repo, leave it alone —
    # the repo IS the source of truth in that case, no copy needed.
    if dst.exists() and (dst.is_symlink() or _is_junction(dst)):
        _skip("slash commands - dst is a link/junction; skipping copy")
        return
    dst.mkdir(exist_ok=True)
    new = upd = same = 0
    for md in src.glob("*.md"):
        target = dst / md.name
        if not target.exists():
            shutil.copy2(md, target); new += 1
        elif md.read_bytes() != target.read_bytes():
            shutil.copy2(md, target); upd += 1
        else:
            same += 1
    _ok(f"slash commands synced to global - {new} new, {upd} updated, {same} unchanged")


def _is_junction(path: Path) -> bool:
    # NTFS junctions don't report as symlinks on older Python; treat any
    # reparse-pointed dir as a link. Cheap inspection: stat the dir and
    # check if its realpath differs from its declared path.
    try:
        return path.resolve(strict=False) != path
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Settings.json: env + statusLine + hooks.
# ---------------------------------------------------------------------------
def _statusline_cmd() -> str:
    """Build the status line command using the current Python interpreter.

    Uses the interpreter that ran setup.py — portable across venvs and platforms.
    CLAUDEBOOST_HOME is expanded at runtime from the env var (set in settings.json env).
    """
    interp = Path(sys.executable).as_posix()
    return f'"{interp}" "$CLAUDEBOOST_HOME/scripts/rag-statusline.py"'


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        _warn("settings.json not found - creating minimal config")
        return {}
    try:
        return read_json(SETTINGS_PATH, {})
    except json.JSONDecodeError:
        _err("settings.json is malformed JSON — validate or delete it and re-run setup.")
        _err(f"  Path: {SETTINGS_PATH}")
        sys.exit(1)


def _script_path(name: str) -> str:
    """Absolute POSIX path to a script in scripts/. Used in hook commands."""
    return (BOOST_HOME / "scripts" / name).as_posix()


def _py_cmd(script_name: str) -> str:
    """Hook command that invokes a script with the current Python interpreter.

    Writing sys.executable avoids the `python` vs `python3` vs venv mess —
    whichever interpreter ran setup is the one used by hooks. Critical on
    macOS/Linux where `python` often doesn't exist (only `python3`).
    """
    interp = Path(sys.executable).as_posix()
    return f'"{interp}" "{_script_path(script_name)}"'


def _hook_command_stale(cmd: str) -> bool:
    """Stale = (1) contains literal $CLAUDEBOOST_HOME bash var, or
    (2) references an absolute script path that no longer exists.

    Paths containing other env-var refs (e.g. $HOME/.claude/ensure-setup.py,
    %APPDATA%\\...) are left alone — we can't verify them without expansion,
    and they are intentionally written that way to stay machine-portable.
    """
    if "$CLAUDEBOOST_HOME" in cmd:
        return True
    import re
    m = re.search(r'"([^"]+\.py)"', cmd)
    if m:
        candidate = m.group(1)
        # Skip paths with unresolved env vars — can't statically verify.
        if "$" in candidate or "%" in candidate:
            return False
        if not Path(candidate).exists():
            return True
    return False


def _clean_stale_hooks(settings: dict) -> None:
    hooks = settings.get("hooks") or {}
    removed = 0
    for hook_type in list(hooks.keys()):
        entries = hooks[hook_type] or []
        new_entries = []
        for entry in entries:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not inner:
                new_entries.append(entry)
                continue
            healthy = []
            for h in inner:
                cmd = h.get("command", "") if isinstance(h, dict) else ""
                if cmd and _hook_command_stale(cmd):
                    preview = cmd[:70]
                    _warn(f"[CLEAN] hooks.{hook_type} - removing stale hook: {preview}...")
                    removed += 1
                else:
                    healthy.append(h)
            if healthy:
                entry["hooks"] = healthy
                new_entries.append(entry)
            # else: entry dropped entirely (every hook in it was stale)
        if new_entries:
            hooks[hook_type] = new_entries
        else:
            del hooks[hook_type]
    settings["hooks"] = hooks
    if removed:
        _ok(f"Removed {removed} stale hook(s)")
    else:
        _ok("No stale hooks found")


def _install_hook(settings: dict, hook_type: str, entry: dict,
                  sentinel: str, label: str) -> None:
    """Append a hook entry once. Sentinel substring identifies an existing
    install — if found, skip (idempotent on re-run). Matcher updates are
    applied in place if the only thing that changed was the matcher."""
    hooks = settings.setdefault("hooks", {})
    if hook_type not in hooks or not hooks[hook_type]:
        hooks[hook_type] = [entry]
        _ok(f"hooks.{hook_type} - added {label}")
        return
    for e in hooks[hook_type]:
        for h in (e.get("hooks") or []):
            text = (h.get("prompt", "") or "") + (h.get("command", "") or "")
            if sentinel in text:
                # Found existing install. Refresh matcher (and command path)
                # if changed — useful when the install dir moved.
                changed = False
                if "matcher" in entry and e.get("matcher") != entry["matcher"]:
                    e["matcher"] = entry["matcher"]
                    changed = True
                # Refresh command path too — handles repo moves.
                for new_h, old_h in zip(entry["hooks"], e["hooks"]):
                    if new_h.get("command") and new_h["command"] != old_h.get("command"):
                        old_h["command"] = new_h["command"]
                        changed = True
                if changed:
                    _ok(f"hooks.{hook_type} - refreshed {label}")
                else:
                    _skip(f"hooks.{hook_type} - {label} already installed")
                return
    hooks[hook_type].append(entry)
    _ok(f"hooks.{hook_type} - appended {label}")


# Hook prompts are kept verbatim from setup.ps1 — sentinels must match so
# re-running this script never duplicates an entry that the PowerShell
# version installed previously.
def _install_all_hooks(settings: dict) -> None:
    _info("\nCleaning up stale hooks...")
    _clean_stale_hooks(settings)

    # --- SessionStart: workflow routing ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{
            "type": "prompt",
            "prompt": ("Quality-first routing: Check CLAUDE.md decision flow. For each action, "
                       "pick the RIGHT approach — not the cheapest, not the most ceremonial. "
                       "Full ceremony where quality demands it (reviews, security, architecture). "
                       "Lightweight where it doesn't (explore, research, docs). Always use "
                       "evaluator-agent for finding verification — never self-verify findings "
                       "(confirmation bias). Rework costs more than doing it right."),
            "statusMessage": "Loading ClaudeBoost workflow...",
            "timeout": 15,
        }],
    }, sentinel="Quality-first routing", label="workflow routing")

    # --- SessionStart: CONSULT mode protocol ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{
            "type": "prompt",
            "prompt": (
                "CLAUDEBOOST MODE — CONSULT vs AUTO:\n\n"
                "Read `$CLAUDEBOOST_HOME/state/claudeboost-mode.json at the start of each task. "
                "Field: ``mode``. Default CONSULT.\n\n"
                "If mode=CONSULT, for any architectural decision you MUST:\n"
                "  1. POST http://127.0.0.1:8612/search (feature keywords) + read 2-3 project files. Cite file:line.\n"
                "  2. Spawn architect-agent (Opus) via Task with ``PROPOSAL_ONLY — citations: ...``.\n"
                "  3. Present 2-3 options via AskUserQuestion. User picks/edits/adds.\n"
                "  4. Log approval to `$CLAUDEBOOST_HOME/state/session-approvals.json.\n"
                "  5. Implement. RAG-required standards apply automatically.\n\n"
                "Architectural = new endpoint, new class/module, new DB table, new dep, new middleware, "
                "auth/validation/error/logging strategy, new public API, new config surface, "
                "new concurrency model.\n\n"
                "NOT architectural = typo, 1-line fix, test, doc, value-only config tweak, "
                "rename in one file, edits under workspace/ .claude/ knowledge/ plans/ docs/.\n\n"
                "Consultation is ADDITIVE, not gatekeeping. Present what RAG requires as already-handled; "
                "invite the user to ADD constraints (size caps, character allowlists, rate limits). "
                "Do not debate whether to validate.\n\n"
                "Check session-approvals.json before spawning architect-agent — if this axis was "
                "already decided, proceed with the approved choice.\n\n"
                "If mode=AUTO: proceed autonomously, still cite sources."
            ),
            "statusMessage": "Loading CONSULT mode protocol...",
        }],
    }, sentinel="CONSULT vs AUTO", label="CONSULT protocol")

    # --- SessionStart: codebase RAG reminder ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{
            "type": "prompt",
            "prompt": ("RAG HTTP API: The RAG server runs on http://127.0.0.1:8612. "
                       "All RAG access uses HTTP — no MCP tools are needed. "
                       "Key endpoints: POST /context (load agent context), "
                       "POST /search (semantic + graph search), "
                       "GET /status (server health), "
                       "POST /index (reindex files). "
                       "When loading context for an agent, POST to /context with "
                       "{\"agent\":\"...\",\"task_description\":\"...\",\"project_path\":\"...\",\"workspace_path\":\"...\"} "
                       "where project_path is the primary working directory (enables Tier 4 codebase search + stack detection) "
                       "and workspace_path is the active workspace directory e.g. $CLAUDEBOOST_HOME/workspace/[task-id] "
                       "(enables Tier 3c task-specific research). Omit workspace_path only if no workspace exists. "
                       "When searching code, POST to /search with "
                       "{\"query\":\"...\",\"scope\":\"codebase\",\"project_path\":\"...\"}. "
                       "If the project has not been indexed, run /index-project first. "
                       "Use mode=graph for import and dependency chains."),
            "statusMessage": "Loading RAG HTTP API config...",
        }],
    }, sentinel="RAG HTTP API", label="RAG HTTP API config")

    # --- SessionStart: compaction restore ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{
            "type": "command",
            "command": _py_cmd("compaction-restore.py"),
            "timeout": 5000,
            "statusMessage": "Restoring context after compaction...",
        }],
    }, sentinel="compaction-restore.py", label="compaction restore (command-type)")

    # --- SessionStart: workspace primer ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{
            "type": "command",
            "command": _py_cmd("workspace-primer.py"),
            "timeout": 5000,
            "statusMessage": "Loading workspace tier briefing...",
        }],
    }, sentinel="workspace-primer.py", label="workspace tier primer (command-type)")

    # --- PreToolUse: agent-spawn gate on Task (command-type) ---
    _install_hook(settings, "PreToolUse", {
        "matcher": "Task",
        "hooks": [{"type": "command", "command": _py_cmd("agent-spawn-gate.py")}],
    }, sentinel="agent-spawn-gate.py", label="Task RAG/proposal gate (command-type)")

    # --- PreToolUse: workspace boost gate (blocks mkdir workspace/* if /boost not run) ---
    _install_hook(settings, "PreToolUse", {
        "matcher": "Bash(mkdir*workspace*)",
        "hooks": [{"type": "command", "command": _py_cmd("workspace-boost-gate.py")}],
    }, sentinel="workspace-boost-gate.py", label="workspace boost gate (command-type)")

    # --- PreToolUse: workspace creation (prompt-type) ---
    _install_hook(settings, "PreToolUse", {
        "matcher": "Bash(mkdir*workspace*)",
        "hooks": [{
            "type": "prompt",
            "prompt": ("WORKSPACE CREATION CHECK: You are creating a workspace directory. "
                       "Before proceeding:\n"
                       "1. Call POST http://127.0.0.1:8612/search with the task description to find relevant knowledge\n"
                       "2. Ensure you have a task ID and will create context.md after this\n"
                       "This is the start of complex work. RAG should be active."),
            "statusMessage": "Enforcing RAG lookup on workspace creation...",
        }],
    }, sentinel="WORKSPACE CREATION CHECK", label="workspace creation")

    # --- PreToolUse: CONSULT gate on Edit/Write/Bash (command-type) ---
    _install_hook(settings, "PreToolUse", {
        "matcher": "Edit|Write|MultiEdit|Bash",
        "hooks": [{"type": "command", "command": _py_cmd("consult-gate.py")}],
    }, sentinel="consult-gate.py", label="CONSULT gate on Edit/Write/Bash (command-type)")

    # --- PreToolUse: Bash guard (blocks commands that trigger permission prompts) ---
    _install_hook(settings, "PreToolUse", {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": _py_cmd("bash-guard.py")}],
    }, sentinel="bash-guard.py", label="Bash guard (command-type)")

    # --- PreToolUse: process-kill safety ---
    _install_hook(settings, "PreToolUse", {
        "matcher": "Bash(pkill*)|Bash(killall*)|Bash(*Stop-Process*)|Bash(*taskkill*/IM*)",
        "hooks": [{
            "type": "prompt",
            "prompt": ("PROCESS KILL SAFETY — STOP and check:\n\n"
                       "You are about to run a process-killing command. Broad name-pattern kills "
                       "(pkill NAME, killall NAME, Stop-Process -Name NAME, taskkill /IM NAME) "
                       "can kill the user's unrelated processes. This has burned the user before.\n\n"
                       "REQUIRED:\n"
                       "- If you have a specific PID, use it: kill PID, Stop-Process -Id PID, "
                       "taskkill /PID pid.\n"
                       "- If targeting a container, use the explicit container name: docker stop NAME.\n"
                       "- If you have only a name pattern and no PID, STOP and ask the user first. "
                       "Never assume it is safe to broad-match.\n\n"
                       "Reason: prior incidents where broad kills hit unrelated processes. Specific "
                       "PIDs or explicit container names only; never broad name patterns without "
                       "explicit user approval."),
            "statusMessage": "Process kill safety check...",
        }],
    }, sentinel="PROCESS KILL SAFETY", label="process kill safety")

    # --- PostToolUse: verify gate (command-type, non-blocking) ---
    # Replaces the old prompt-type hook which blocked batched agent flows
    # (code-review passes ground to a halt waiting for Claude to respond).
    # verify-gate-cmd.py emits a stderr nudge only when findings are present,
    # and suppresses during code-review pass runs where Pass 15 handles it.
    _install_hook(settings, "PostToolUse", {
        "matcher": "Task",
        "hooks": [{"type": "command", "command": _py_cmd("verify-gate-cmd.py"),
                   "timeout": 3000, "statusMessage": "Checking agent output for findings..."}],
    }, sentinel="verify-gate-cmd.py", label="verify gate (command-type)")

    # --- PostToolUse: context nudge (counter-based, all tools) ---
    _install_hook(settings, "PostToolUse", {
        "matcher": ".*",
        "hooks": [{"type": "command", "command": _py_cmd("context-nudge.py"), "timeout": 3000}],
    }, sentinel="context-nudge.py", label="context nudge (command-type)")

    # --- PostToolUse: comment humanness check (Edit/Write) ---
    _install_hook(settings, "PostToolUse", {
        "matcher": "Edit|Write",
        "hooks": [{"type": "command", "command": _py_cmd("comment-humanness-check.py"), "timeout": 5000}],
    }, sentinel="comment-humanness-check.py", label="comment humanness check (command-type)")

    # --- PreCompact: context preservation + compaction save ---
    _install_hook(settings, "PreCompact", {
        "matcher": "Always",
        "hooks": [
            {
                "type": "prompt",
                "prompt": ("CONTEXT PRESERVATION — quality-first routing:\n"
                           "1. Agent spawns: call POST http://127.0.0.1:8612/context (Step 1), route by type "
                           "(full/standard/lightweight)\n"
                           "2. Finding verification: ALWAYS evaluator-agent, never self-verify "
                           "(confirmation bias)\n"
                           "3. Decision flow: simple (just do it) vs complex (workspace + agents)\n"
                           "4. Rework costs more than ceremony. Do it right the first time.\n"
                           "5. CONSULT/AUTO mode file at `$CLAUDEBOOST_HOME/state/claudeboost-mode.json "
                           "— re-check after compact. Default CONSULT: research + propose + ask "
                           "before architectural decisions."),
                "statusMessage": "Preserving RAG/CONSULT awareness before compaction...",
            },
            {
                "type": "command",
                "command": _py_cmd("compaction-save.py"),
                "timeout": 5000,
                "statusMessage": "Saving working state before compaction...",
            },
        ],
    }, sentinel="CONTEXT PRESERVATION", label="context preservation + compaction save")

    # --- SessionEnd: clear handoff save ---
    _install_hook(settings, "SessionEnd", {
        "hooks": [{"type": "command", "command": _py_cmd("session-clear-save.py")}],
    }, sentinel="session-clear-save.py", label="clear handoff save")

    # --- UserPromptSubmit: ensure-setup bootstrap ---
    # Copy ensure-setup.py to ~/.claude/ so $HOME-relative path works on every machine.
    ensure_src = BOOST_HOME / "scripts" / "ensure-setup.py"
    ensure_dst = CLAUDE_DIR / "ensure-setup.py"
    shutil.copy2(ensure_src, ensure_dst)
    _ok(f"ensure-setup.py copied to {ensure_dst}")

    # The hook command uses $HOME so it doesn't bake in a machine-specific
    # absolute path. Wrap interpreter in quotes for paths with spaces.
    interp = Path(sys.executable).as_posix()
    ensure_cmd = f'"{interp}" "$HOME/.claude/ensure-setup.py"'
    _install_hook(settings, "UserPromptSubmit", {
        "hooks": [{"type": "command", "command": ensure_cmd, "timeout": 10000}],
    }, sentinel="ensure-setup.py", label="auto-setup bootstrap")

    # --- UserPromptSubmit: TTS interrupt ---
    _install_hook(settings, "UserPromptSubmit", {
        "hooks": [{"type": "command", "command": _py_cmd("speak-stop.py"), "timeout": 3000}],
    }, sentinel="speak-stop.py", label="TTS interrupt (command-type)")

    # --- Stop: auto-clear (fires /clear after /clear-safe sets the pending flag) ---
    _install_hook(settings, "Stop", {
        "hooks": [{"type": "command", "command": _py_cmd("auto-clear.py")}],
    }, sentinel="auto-clear.py", label="auto-clear")

    # --- Stop: TTS speak hook ---
    _install_hook(settings, "Stop", {
        "hooks": [{"type": "command", "command": _py_cmd("speak-tts.py")}],
    }, sentinel="speak-tts.py", label="TTS speak hook")


def update_settings() -> None:
    settings = _load_settings()

    # CLAUDEBOOST_HOME env entry
    env = settings.setdefault("env", {})
    env["CLAUDEBOOST_HOME"] = BOOST_HOME_POSIX

    # statusLine — always use the Python-based RAG health script (cross-platform)
    new_sl_cmd = _statusline_cmd()
    sl = settings.get("statusLine")
    if isinstance(sl, dict) and sl.get("command") == new_sl_cmd:
        _skip("statusLine - already configured")
    else:
        settings["statusLine"] = {"type": "command", "command": new_sl_cmd}
        _ok("statusLine - configured RAG health indicator")

    _install_all_hooks(settings)

    write_json(SETTINGS_PATH, settings)
    _ok("settings.json - CLAUDEBOOST_HOME env added")


# ---------------------------------------------------------------------------
# Subprocess helper: run a native command without letting stderr trigger
# PowerShell-style exceptions. Returns exit code + merged output.
# ---------------------------------------------------------------------------
def run_cmd(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except FileNotFoundError as e:
        return 127, str(e)


def _pip_cmd() -> list[str]:
    """Prefer `python -m pip` over a bare `pip` binary — guarantees the pip
    that ships with our interpreter, avoids `pip is not on PATH` on macOS."""
    return [sys.executable, "-m", "pip"]


def _pip_install(args: list[str]) -> tuple[int, str]:
    """pip install with PEP 668 fallback.

    Homebrew / Debian Python ships with `EXTERNALLY-MANAGED`, which blocks
    system-wide pip installs. When we see that error, retry once with
    `--user --break-system-packages` so the install lands in `~/.local`
    without modifying the system / Homebrew Python. Users who prefer a venv
    can activate one before running setup — this fallback only fires when
    no venv is active.
    """
    rc, out = run_cmd(_pip_cmd() + ["install"] + args)
    if rc == 0:
        return rc, out
    if "externally-managed-environment" in out or "PEP 668" in out:
        _warn("pip is externally-managed (PEP 668). Retrying with --user --break-system-packages...")
        rc, out = run_cmd(_pip_cmd() + ["install", "--user", "--break-system-packages"] + args)
    return rc, out


# ---------------------------------------------------------------------------
# RAG server install + health check.
# ---------------------------------------------------------------------------
def install_rag_server() -> None:
    _info("\nVerifying RAG server...")
    rag_dir = BOOST_HOME / "mcp-rag-server"
    _info(f"Installing RAG server from {rag_dir} (editable mode)...")
    rc, out = _pip_install(["-e", str(rag_dir)])
    if rc != 0:
        _warn(f"pip install returned exit code {rc}")
        if out:
            _warn(out)
        _warn(f"  Run manually: {' '.join(_pip_cmd())} install -e {rag_dir}")
    else:
        _ok("RAG server installed (editable mode)")

    _info("Installing optional graph deps (graspologic + networkx)...")
    rc_graph, out_graph = _pip_install(["-e", f"{rag_dir}[graph]"])
    if rc_graph != 0:
        _warn("graspologic install failed — community detection will be skipped (non-fatal)")
        _warn("  To install manually: pip install 'rag-server[graph]'")
    else:
        _ok("Graph extras installed (graspologic + networkx)")

    _info("Installing optional SCIP deps (scip-python for type-resolved edges)...")
    rc_scip, out_scip = _pip_install(["-e", f"{rag_dir}[scip]"])
    if rc_scip != 0:
        _warn("scip-python install failed — SCIP graph edges will be skipped (non-fatal)")
        _warn("  To install manually: pip install 'rag-server[scip]'")
    else:
        _ok("SCIP extras installed (scip-python)")

    _info("Upgrading ML deps (sentence-transformers + transformers + tokenizers)...")
    rc, out = _pip_install([
        "--upgrade", "--upgrade-strategy", "eager",
        "sentence-transformers", "transformers", "tokenizers",
    ])
    if rc != 0:
        _warn(f"ML-deps upgrade returned exit code {rc}")
        if out:
            _warn(out)
    else:
        _ok("ML deps upgraded")

    # Drop torchvision if it's incompatible with the installed torch (CPU torch
    # + CUDA torchvision = ImportError that breaks sentence_transformers).
    rc, _ = run_cmd([sys.executable, "-c", "import torchvision"])
    if rc != 0:
        _warn("torchvision import failed — uninstalling incompatible build...")
        rc, _ = run_cmd(_pip_cmd() + ["uninstall", "torchvision", "-y"])
        if rc == 0:
            _ok("torchvision removed")
        else:
            _warn("Could not remove torchvision")

    _info("Installing HTTP server deps (starlette + uvicorn)...")
    rc, out = _pip_install(["starlette>=0.37", "uvicorn[standard]>=0.29"])
    if rc != 0:
        _warn(f"starlette/uvicorn install failed: {out}")
    else:
        _ok("HTTP server deps installed (starlette + uvicorn)")

    health_script = BOOST_HOME / "scripts" / "check-rag-health.py"
    rc, out = run_cmd([sys.executable, str(health_script)])
    if rc == 0:
        _ok(f"RAG modules healthy: {out}")
    else:
        _warn(f"RAG health check failed (exit {rc})")
        if out:
            _warn(out)
        _warn(f"  Run manually: {sys.executable} {BOOST_HOME / 'scripts' / 'reinstall-rag.py'}")

    # Start the HTTP server as background daemon
    _info("Starting RAG HTTP server (port 8612)...")
    start_script = BOOST_HOME / "scripts" / "rag-server-start.py"
    rc, out = run_cmd([sys.executable, str(start_script)])
    if rc == 0:
        _ok(f"RAG HTTP server running: {out.splitlines()[-1] if out else 'port 8612'}")
    else:
        _warn("RAG HTTP server did not start — run it manually:")
        _warn(f"  {sys.executable} \"{start_script}\"")

    # Clean up any stale MCP registration (idempotent)
    _cleanup_mcp_registration()


# ---------------------------------------------------------------------------
# MCP cleanup: remove rag-server from `claude mcp` if it was registered by an
# older setup. The RAG server is now accessed entirely via HTTP on port 8612.
# ---------------------------------------------------------------------------
def _cleanup_mcp_registration() -> None:
    """Remove the rag-server MCP registration if it still exists.

    Idempotent — safe to run multiple times. The RAG server no longer uses MCP;
    it runs as a standalone HTTP daemon on port 8612.
    """
    # Try `claude mcp list` to see current configs
    rc, out = run_cmd(["claude", "mcp", "list"])
    if rc != 0:
        _skip("claude CLI not found — skipping MCP cleanup")
        return

    if "rag-server" not in out:
        _skip("MCP config - rag-server not registered, nothing to remove")
        return

    # Remove the rag-server entry (try with scope flag first)
    rc_rm, _ = run_cmd(["claude", "mcp", "remove", "rag-server", "--scope", "user"])
    if rc_rm != 0:
        rc_rm, _ = run_cmd(["claude", "mcp", "remove", "rag-server"])
    if rc_rm == 0:
        _ok("MCP config - removed stale rag-server entry (RAG is HTTP-only now)")
    else:
        _warn("Could not remove rag-server from MCP config — remove it manually: "
              "claude mcp remove rag-server")


# ---------------------------------------------------------------------------
# mcp-debugger: register with `claude mcp` at user scope so it's available
# in every Claude session. Idempotent — skips if already registered.
# ---------------------------------------------------------------------------
def register_mcp_debugger() -> None:
    _info("\nVerifying mcp-debugger...")
    rc, out = run_cmd(["claude", "mcp", "list"])
    if rc != 0:
        _skip("claude CLI not found — skipping mcp-debugger registration")
        return

    if "mcp-debugger" in out:
        if "Connected" in out or "connected" in out:
            _ok("mcp-debugger already registered and connected")
        else:
            _warn("mcp-debugger registered but not connected — ensure Node 22+ is installed")
        return

    _info("Registering mcp-debugger (user scope)...")
    rc, out = run_cmd([
        "claude", "mcp", "add", "mcp-debugger",
        "--scope", "user",
        "--", "npx", "-y", "@debugmcp/mcp-debugger", "stdio",
    ])
    if rc == 0:
        _ok("mcp-debugger registered — run /mcp to connect")
    else:
        _warn(f"mcp-debugger registration failed (exit {rc})")
        if out:
            _warn(f"  {out[:200]}")
        _warn("  To register manually: claude mcp add mcp-debugger --scope user -- npx -y @debugmcp/mcp-debugger stdio")


# ---------------------------------------------------------------------------
# edge-tts: install on Windows and macOS only. Linux is intentionally skipped
# per the macOS/Linux support plan (TTS playback is not supported there).
# ---------------------------------------------------------------------------
def install_edge_tts() -> None:
    if IS_LINUX:
        _info("\nSkipping edge-tts — /speak is not supported on Linux.")
        return
    _info("\nVerifying edge-tts...")
    rc, out = run_cmd([sys.executable, "-c", "import edge_tts; print('ok')"])
    if rc == 0 and out.strip() == "ok":
        _ok("edge-tts already installed")
        return
    _info("Installing edge-tts...")
    rc, out = _pip_install(["edge-tts"])
    if rc == 0:
        _ok("edge-tts installed")
    else:
        _warn(f"edge-tts install failed - /speak will not work until you run: "
              f"{' '.join(_pip_cmd())} install edge-tts")
        if out:
            _warn(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    _info("\n=== ClaudeBoost Setup ===")
    print(f"ClaudeBoost home: {BOOST_HOME}")
    print(f"Claude config dir: {CLAUDE_DIR}")
    print(f"Platform: {platform.system()} ({sys.platform})\n")

    if not preflight():
        print()
        _err("Required tools missing. Fix the above and re-run setup.")
        return 1

    CLAUDE_DIR.mkdir(exist_ok=True)
    update_mcp_configs()
    sync_slash_commands()
    seed_state()
    update_settings()
    install_rag_server()
    register_mcp_debugger()
    install_edge_tts()

    _info("\n=== Setup Complete ===")
    print(f"  CLAUDEBOOST_HOME = {BOOST_HOME_POSIX}")
    print( "  RAG HTTP server started on port 8612")
    print( "  Hooks configured (SessionStart, SessionEnd, PreToolUse, PostToolUse, "
           "PreCompact, UserPromptSubmit, Stop)")
    _say("\nNext steps:", "yellow")
    print("  1. Run /rag in Claude Code to verify the RAG server")
    print("  2. Run /boost to verify all systems")
    if not IS_LINUX:
        print("  3. Run /speak on to enable text-to-speech")
    print("")
    _say("Troubleshooting:", "yellow")
    print("  If Claude Code is completely blocked (UserPromptSubmit hook error):")
    print(f"  Run fix_hooks first, then re-run setup:")
    print(f"    {sys.executable} {BOOST_HOME / 'scripts' / 'fix_hooks.py'}")
    print(f"    {sys.executable} {BOOST_HOME / 'scripts' / 'setup.py'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
