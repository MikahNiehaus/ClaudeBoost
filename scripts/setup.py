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
 11. Installs netcoredbg from Samsung GitHub releases so mcp-debugger can step
     through .NET/C# code. Adds the binary to the user PATH (winreg on Windows,
     ~/.profile on macOS/Linux). Skipped if dotnet SDK is not present.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
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

    enforcement_path = state_dir / "rag-enforcement.json"
    if not enforcement_path.exists():
        write_json(enforcement_path, {"enabled": True, "setAt": now, "setBy": "default"})
        _ok("state/rag-enforcement.json - seeded enforcement enabled default")
    else:
        _skip("state/rag-enforcement.json - preserving existing setting")


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
    """Build the status line command with same fallback chain as _py_cmd."""
    script = '"$CLAUDEBOOST_HOME/scripts/rag-statusline.py"'
    return (
        f'"$CLAUDEBOOST_PYTHON" {script}'
        f' || python {script}'
        f' || python3 {script}'
        f' || py {script}'
    )


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


def _py_cmd(script_name: str, base_dir: str = "scripts") -> str:
    """Hook command that invokes a ClaudeBoost script.

    Resolves the working Python launcher ONCE via `command -v` (an existence
    check, not an execution), then runs the script exactly once so its real
    exit code (0 pass / 2 block / etc.) propagates untouched. Falls back
    through python3 / python / py in case $CLAUDEBOOST_PYTHON isn't valid on
    this machine (e.g. after a machine move where settings.json still has
    the old machine's Python path baked in).

    Earlier versions chained with `A || B || C || D`. Bash's `||` can't tell
    "the interpreter wasn't found" apart from "the script ran fine and
    deliberately exited non-zero to block a tool call" (exit code 2 is
    Claude Code's documented PreToolUse block signal) — both are non-zero,
    so any legitimate block re-ran the next fallback against
    already-drained stdin, producing duplicate/contradictory hook output
    (and, for scripts with input-order bugs, a crash on the retry).
    Checking with `command -v` first avoids ever running the script twice.
    """
    script = f'"$CLAUDEBOOST_HOME/{base_dir}/{script_name}"'
    return (
        f'if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then "$CLAUDEBOOST_PYTHON" {script}; '
        f'elif command -v python3 >/dev/null 2>&1; then python3 {script}; '
        f'elif command -v python >/dev/null 2>&1; then python {script}; '
        f'else py {script}; fi'
    )


def _hook_command_stale(cmd: str) -> bool:
    """Stale = references an absolute script path that no longer exists.

    Commands using env-var refs ($CLAUDEBOOST_PYTHON, $CLAUDEBOOST_HOME, $HOME,
    %APPDATA%, etc.) are portable and left alone — can't verify statically, and
    they're intentionally written that way.
    """
    import re
    m = re.search(r'"([^"]+\.py)"', cmd)
    if m:
        candidate = m.group(1)
        # Env-var-relative paths are portable — skip
        if "$" in candidate or "%" in candidate:
            return False
        # Absolute path that's gone — stale
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


# Prompt-type hooks replaced by command-type scripts. The old entries linger in
# settings.json from earlier installs and keep firing alongside the replacement:
# the prompt-type VERIFY GATE blocks continuation after every agent spawn, which
# is exactly what verify-gate-cmd.py was written to stop.
_SUPERSEDED_PROMPT_SENTINELS = (
    "VERIFY GATE: Scan agent output",       # replaced by verify-gate-cmd.py
    "AGENT SPAWN QUALITY ROUTING",          # replaced by agent-spawn-gate.py
)


def _remove_superseded_hooks(settings: dict) -> None:
    hooks = settings.get("hooks") or {}
    removed = 0
    for hook_type in list(hooks.keys()):
        new_entries = []
        for entry in hooks[hook_type] or []:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not inner:
                new_entries.append(entry)
                continue
            healthy = []
            for h in inner:
                text = (h.get("prompt", "") or "") if isinstance(h, dict) else ""
                if text and any(s in text for s in _SUPERSEDED_PROMPT_SENTINELS):
                    _warn(f"[CLEAN] hooks.{hook_type} - removing superseded prompt hook: {text[:60]}...")
                    removed += 1
                else:
                    healthy.append(h)
            if healthy:
                entry["hooks"] = healthy
                new_entries.append(entry)
        if new_entries:
            hooks[hook_type] = new_entries
        else:
            del hooks[hook_type]
    settings["hooks"] = hooks
    if removed:
        _ok(f"Removed {removed} superseded prompt hook(s)")


# Command-type hooks whose target script was removed upstream. A hook pointing at
# a missing .py exits non-zero and BLOCKS every matching tool call, so these must
# be stripped from old installs. git-guard.py was dropped (the static git ask-list
# in permissions covers the same ground); its leftover hook broke every Bash git
# command until removed. _clean_stale_hooks can't catch these because it skips
# env-var paths ($CLAUDEBOOST_HOME/...), so we match by basename instead.
_REMOVED_HOOK_SCRIPTS = (
    "git-guard.py",
)


def _remove_deleted_script_hooks(settings: dict) -> None:
    hooks = settings.get("hooks") or {}
    removed = 0
    for hook_type in list(hooks.keys()):
        new_entries = []
        for entry in hooks[hook_type] or []:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not inner:
                new_entries.append(entry)
                continue
            healthy = []
            for h in inner:
                cmd = (h.get("command", "") or "") if isinstance(h, dict) else ""
                if cmd and any(name in cmd for name in _REMOVED_HOOK_SCRIPTS):
                    _warn(f"[CLEAN] hooks.{hook_type} - removing hook for deleted script: {cmd[:70]}...")
                    removed += 1
                else:
                    healthy.append(h)
            if healthy:
                entry["hooks"] = healthy
                new_entries.append(entry)
        if new_entries:
            hooks[hook_type] = new_entries
        else:
            del hooks[hook_type]
    settings["hooks"] = hooks
    if removed:
        _ok(f"Removed {removed} hook(s) for deleted scripts")


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


# ---------------------------------------------------------------------------
# clean-rag bundled integration: when clean-rag/ exists alongside ClaudeBoost,
# main() runs its installer (install_clean_rag below). setup.py detects it but
# does not register clean-rag's hooks itself, clean-rag/install.py owns those.
# ---------------------------------------------------------------------------
def _clean_rag_detected() -> bool:
    return (BOOST_HOME / "clean-rag" / "install.py").exists()


def _clean_rag_home_posix() -> str:
    return (BOOST_HOME / "clean-rag").as_posix()


# setup.py used to hand register clean-rag's hooks itself, and it went stale:
# it wired proof-gate.py (deleted, now a placeholder stub) and a pending-proof
# workflow that no longer exists. Rather than keep a second copy of clean-rag's
# hook list in sync by hand, ClaudeBoost setup now just runs clean-rag's own
# installer, which is the single source of truth for the current gate
# (research-gate, research-record, rag-enforce, reindex, code-pattern-inject,
# graph-context-inject) and also copies the agents, skills, and hook launcher
# into ~/.claude. clean-rag/install.py is idempotent, so this is safe to re-run.
def install_clean_rag() -> None:
    if not _clean_rag_detected():
        _say("clean-rag not present, skipping", "yellow")
        return

    installer = BOOST_HOME / "clean-rag" / "install.py"
    _say(f"Running clean-rag installer: {installer}")
    code, out = run_cmd([sys.executable, str(installer)])
    if out:
        for line in out.splitlines():
            print(f"    {line}")
    if code == 0:
        _ok("clean-rag installed")
    else:
        _err(f"clean-rag installer exited {code}")


# Hook prompts are kept verbatim from setup.ps1 — sentinels must match so
# re-running this script never duplicates an entry that the PowerShell
# version installed previously.
def _install_all_hooks(settings: dict) -> None:
    _info("\nCleaning up stale hooks...")
    _clean_stale_hooks(settings)
    _remove_superseded_hooks(settings)
    _remove_deleted_script_hooks(settings)

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

    # --- SessionStart: RAG session reset (clears sentinel for fresh session verification) ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{
            "type": "command",
            "command": _py_cmd("rag-session-reset.py"),
            "timeout": 3000,
            "statusMessage": "Resetting RAG sentinel for fresh session verification...",
        }],
    }, sentinel="rag-session-reset.py", label="RAG session reset (command-type)")

    # --- PreToolUse: agent-spawn gate on Task (command-type) ---
    # Lives under clean-rag/hooks/, but enforces
    # core ClaudeBoost RAG (port 8612) — installed unconditionally here, not
    # gated behind _clean_rag_detected(), since it's not a clean-rag-specific
    # concern even though it's physically colocated with clean-rag's hooks.
    _install_hook(settings, "PreToolUse", {
        "matcher": "Task",
        "hooks": [{"type": "command", "command": _py_cmd("agent-spawn-gate.py", base_dir="clean-rag/hooks")}],
    }, sentinel="agent-spawn-gate.py", label="Task RAG/proposal gate (command-type)")

    # --- PreToolUse: skill verify gate on Skill tool ---
    # Blocks action skills (qa, workspace, explore, etc.) when needs-verification.json
    # is pending. Companion to agent-spawn-gate — that gate only fires on Task spawns.
    _install_hook(settings, "PreToolUse", {
        "matcher": "Skill",
        "hooks": [{"type": "command", "command": _py_cmd("skill-verify-gate.py")}],
    }, sentinel="skill-verify-gate.py", label="Skill verify gate (command-type)")

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

    # --- PreToolUse: TDD guard (blocks source edits without test changes) ---
    # Default mode is "soft" (nudge, not block) until user opts into strict.
    _install_hook(settings, "PreToolUse", {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": _py_cmd("tdd-guard.py")}],
    }, sentinel="tdd-guard.py", label="TDD guard (command-type)")

    # clean-rag hooks are no longer registered here. When clean-rag is present,
    # main() runs its own installer (install_clean_rag), which owns the current
    # hook list. Registering them here too would just duplicate and drift.

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
    # (/review --deep passes ground to a halt waiting for Claude to respond).
    # verify-gate-cmd.py emits a stderr nudge only when findings are present,
    # and suppresses during /review --deep pass runs where Pass 15 handles it.
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

    # --- PostToolUse: comment humanness check (Edit/Write/MultiEdit) ---
    _install_hook(settings, "PostToolUse", {
        "matcher": "Edit|Write|MultiEdit",
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

    # --- PreCompact: Low Token Mode handler ---
    _install_hook(settings, "PreCompact", {
        "matcher": "Always",
        "hooks": [
            {
                "type": "command",
                "command": _py_cmd("lt-precompact.py"),
                "timeout": 8000,
                "statusMessage": "Checking Low Token Mode...",
            },
        ],
    }, sentinel="lt-precompact.py", label="Low Token Mode precompact handler")

    # --- SessionEnd: clear handoff save ---
    _install_hook(settings, "SessionEnd", {
        "hooks": [{"type": "command", "command": _py_cmd("session-clear-save.py")}],
    }, sentinel="session-clear-save.py", label="clear handoff save")

    # --- Telemetry: session lifecycle (SessionStart creates session.json, SessionEnd closes it) ---
    _install_hook(settings, "SessionStart", {
        "matcher": "Always",
        "hooks": [{"type": "command", "command": _py_cmd("telemetry-session.py"), "timeout": 3000,
                   "statusMessage": "Opening telemetry session..."}],
    }, sentinel="telemetry-session.py", label="telemetry session lifecycle")

    _install_hook(settings, "SessionEnd", {
        "hooks": [{"type": "command", "command": _py_cmd("telemetry-session.py"), "timeout": 3000}],
    }, sentinel="telemetry-session.py", label="telemetry session end")

    # --- Telemetry: PostToolUse action log (all tools -> claude-actions.jsonl) ---
    _install_hook(settings, "PostToolUse", {
        "matcher": ".*",
        "hooks": [{"type": "command", "command": _py_cmd("telemetry-hook.py"), "timeout": 3000,
                   "statusMessage": "Logging tool call..."}],
    }, sentinel="telemetry-hook.py", label="telemetry action log")

    # --- UserPromptSubmit: ensure-setup bootstrap ---
    # Copy ensure-setup.py to ~/.claude/ so $HOME-relative path works on every machine.
    ensure_src = BOOST_HOME / "scripts" / "ensure-setup.py"
    ensure_dst = CLAUDE_DIR / "ensure-setup.py"
    shutil.copy2(ensure_src, ensure_dst)
    _ok(f"ensure-setup.py copied to {ensure_dst}")

    # Fallback chain ensures ensure-setup.py runs even when CLAUDEBOOST_PYTHON
    # still points to the old machine's Python path after a machine move.
    ensure_cmd = (
        '"$CLAUDEBOOST_PYTHON" "$HOME/.claude/ensure-setup.py"'
        ' || python "$HOME/.claude/ensure-setup.py"'
        ' || python3 "$HOME/.claude/ensure-setup.py"'
        ' || py "$HOME/.claude/ensure-setup.py"'
    )
    _install_hook(settings, "UserPromptSubmit", {
        "hooks": [{"type": "command", "command": ensure_cmd, "timeout": 10000}],
    }, sentinel="ensure-setup.py", label="auto-setup bootstrap")

    # --- UserPromptSubmit: session primer (RAG sentinel enforcement) ---
    _install_hook(settings, "UserPromptSubmit", {
        "hooks": [{"type": "command", "command": _py_cmd("session-primer.py"), "timeout": 10000}],
    }, sentinel="session-primer.py", label="RAG session primer (command-type)")

    # research-task-nudge removed: the /research-task command it advertised was
    # retired in favor of the clean-rag research setup.

    # --- UserPromptSubmit: TTS interrupt ---
    _install_hook(settings, "UserPromptSubmit", {
        "hooks": [{"type": "command", "command": _py_cmd("speak-stop.py"), "timeout": 3000}],
    }, sentinel="speak-stop.py", label="TTS interrupt (command-type)")

    # --- UserPromptSubmit: prompt rules injector (RAG locations + behavioral rules) ---
    _install_hook(settings, "UserPromptSubmit", {
        "hooks": [{"type": "command", "command": _py_cmd("prompt-rules-injector.py"), "timeout": 5000}],
    }, sentinel="prompt-rules-injector.py", label="prompt rules injector (command-type)")

    # --- Stop: human voice guard (enforces human voice standard on responses) ---
    _install_hook(settings, "Stop", {
        "hooks": [{"type": "command", "command": _py_cmd("human-voice-guard.py")}],
    }, sentinel="human-voice-guard.py", label="human voice guard (command-type)")

    # --- Stop: rules compliance check (forces explicit rules attestation on every response) ---
    _install_hook(settings, "Stop", {
        "hooks": [{"type": "command", "command": _py_cmd("rules-compliance-check.py")}],
    }, sentinel="rules-compliance-check.py", label="rules compliance check (command-type)")

    # --- Stop: auto-clear (fires /clear after /clear-safe sets the pending flag) ---
    _install_hook(settings, "Stop", {
        "hooks": [{"type": "command", "command": _py_cmd("auto-clear.py")}],
    }, sentinel="auto-clear.py", label="auto-clear")

    # --- Stop: TTS speak hook ---
    _install_hook(settings, "Stop", {
        "hooks": [{"type": "command", "command": _py_cmd("speak-tts.py")}],
    }, sentinel="speak-tts.py", label="TTS speak hook")



# ---------------------------------------------------------------------------
# Permission gates: ensure global settings.json has the correct allow/ask/deny
# entries for safe ClaudeBoost operation.
#
# Policy enforced here:
#   allow  — "Bash" catch-all (safe because bash-guard.py PreToolUse hook
#             enforces safety at the command level for every Bash call)
#   ask    — every git/gh write operation; must prompt before modifying repo
#   deny   — hard blocks: force-push main/master, catastrophic destructive ops
#
# All operations are additive. Existing user entries are never removed.
# ---------------------------------------------------------------------------
_GIT_WRITE_ASK = [
    "Bash(git commit **)", "Bash(git commit)",
    "Bash(git push)", "Bash(git push **)",
    "Bash(git push --force **)", "Bash(git push -f **)",
    "Bash(git add **)", "Bash(git add .)", "Bash(git add -A)",
    "Bash(git merge **)", "Bash(git merge)",
    "Bash(git rebase **)", "Bash(git rebase)",
    "Bash(git reset **)", "Bash(git reset)",
    "Bash(git restore **)",
    "Bash(git clean **)",
    "Bash(git checkout **)", "Bash(git checkout)",
    "Bash(git switch **)", "Bash(git switch)",
    "Bash(git stash **)", "Bash(git stash)",
    "Bash(git cherry-pick **)", "Bash(git cherry-pick)",
    "Bash(git revert **)", "Bash(git revert)",
    "Bash(git pull **)", "Bash(git pull)",
    "Bash(git init)", "Bash(git init **)",
    "Bash(git clone **)",
    "Bash(git remote add **)", "Bash(git remote remove **)", "Bash(git remote set-url **)",
    "Bash(git rm **)", "Bash(git mv **)",
    "Bash(git apply **)", "Bash(git am **)",
    "Bash(git worktree **)",
    "Bash(git branch -d **)", "Bash(git branch -m **)", "Bash(git branch -c **)",
    "Bash(git branch --copy **)",
    "Bash(git tag -a **)", "Bash(git tag -d **)", "Bash(git tag --delete **)",
    "Bash(git config --global **)", "Bash(git config --system **)",
    "Bash(git config --local **)", "Bash(git config --unset **)",
    "Bash(git filter-branch **)", "Bash(git filter-repo **)",
    "Bash(git reflog expire **)", "Bash(git reflog delete **)",
    "Bash(git submodule add **)", "Bash(git submodule deinit **)",
    "Bash(git sparse-checkout **)",
    "Bash(git lfs track **)", "Bash(git lfs untrack **)",
    "Bash(git notes add **)", "Bash(git notes edit **)", "Bash(git notes remove **)",
    "Bash(gh pr create **)", "Bash(gh pr edit **)",
    "Bash(gh pr merge **)", "Bash(gh pr close **)",
    "Bash(gh issue create **)", "Bash(gh issue close **)",
    "Bash(gh release **)", "Bash(gh repo create **)",
    "Bash(gh gist create **)", "Bash(gh gist edit **)", "Bash(gh gist delete **)",
]

_GIT_DENY = [
    "Bash(git push --force origin main **)",
    "Bash(git push --force origin master **)",
    "Bash(git push -f origin main **)",
    "Bash(git push -f origin master **)",
    "Bash(git branch -D **)",
    "Bash(git branch --delete --force **)",
    "Bash(git clean -fdx **)",
    "Bash(git clean -fxd **)",
    "Bash(git reset --hard HEAD~ **)",
]

_BASH_CATCHALL = "Bash"


def _update_permissions(settings: dict) -> None:
    """Ensure global settings.json has the correct ClaudeBoost permission entries.

    Additive only — never removes entries the user added themselves.
    """
    perms = settings.setdefault("permissions", {})
    allow: list = perms.setdefault("allow", [])
    ask: list = perms.setdefault("ask", [])
    deny: list = perms.setdefault("deny", [])

    added_allow, added_ask, added_deny = 0, 0, 0

    # "Bash" catch-all must be in allow so common dev commands don't prompt.
    # bash-guard.py (PreToolUse) enforces the real safety policy.
    if _BASH_CATCHALL not in allow:
        allow.insert(0, _BASH_CATCHALL)
        added_allow += 1

    # Every git/gh write operation must prompt.
    for entry in _GIT_WRITE_ASK:
        if entry not in ask:
            ask.append(entry)
            added_ask += 1

    # Hard blocks that should never be auto-approved even if "Bash" is in allow.
    for entry in _GIT_DENY:
        if entry not in deny:
            deny.append(entry)
            added_deny += 1

    if added_allow or added_ask or added_deny:
        _ok(
            f"Permissions: +{added_allow} allow, +{added_ask} ask, "
            f"+{added_deny} deny entries added"
        )
    else:
        _skip("Permissions — all required entries already present")


def update_settings() -> None:
    settings = _load_settings()

    # Env entries used by hook commands — both are machine-specific but set here
    # so the hook command strings themselves stay portable (no baked-in paths).
    env = settings.setdefault("env", {})
    env["CLAUDEBOOST_HOME"] = BOOST_HOME_POSIX
    env["CLAUDEBOOST_PYTHON"] = Path(sys.executable).as_posix()

    # clean-rag bundled mode: set CLEAN_RAG_HOME when clean-rag/ is present
    if _clean_rag_detected():
        env["CLEAN_RAG_HOME"] = _clean_rag_home_posix()
        _ok(f"CLEAN_RAG_HOME set (bundled mode): {_clean_rag_home_posix()}")
    elif "CLEAN_RAG_HOME" in env:
        # clean-rag was removed, clean up the stale env var
        del env["CLEAN_RAG_HOME"]
        _ok("CLEAN_RAG_HOME removed (clean-rag not present)")

    # Write a stable lookup file so ensure-setup.py can find the repo even when
    # it's running from ~/.claude/ (outside the repo tree).
    home_file = CLAUDE_DIR / "claudeboost-home.txt"
    home_file.write_text(BOOST_HOME_POSIX, encoding="utf-8")
    _ok(f"claudeboost-home.txt written: {home_file}")

    # statusLine — always use the Python-based RAG health script (cross-platform)
    new_sl_cmd = _statusline_cmd()
    sl = settings.get("statusLine")
    if isinstance(sl, dict) and sl.get("command") == new_sl_cmd:
        _skip("statusLine - already configured")
    else:
        settings["statusLine"] = {"type": "command", "command": new_sl_cmd}
        _ok("statusLine - configured RAG health indicator")

    _install_all_hooks(settings)
    _update_permissions(settings)

    write_json(SETTINGS_PATH, settings)
    _ok("settings.json - CLAUDEBOOST_HOME env added")


# ---------------------------------------------------------------------------
# Project-level settings cleanup — runs after update_settings() so env vars
# are current. After a repo move, hooks with absolute ClaudeBoost paths in
# project settings.local.json files become stale and block Edit/Write/Bash
# until removed. This makes cleanup automatic on every install.
# ---------------------------------------------------------------------------
def _clean_project_local_settings() -> None:
    reg_path = BOOST_HOME / "state" / "workspaces.json"
    project_paths: set = set()

    try:
        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        for entry in reg.values():
            pp = entry.get("project_path")
            if pp:
                project_paths.add(Path(pp))
    except Exception:
        pass

    project_paths.add(Path.cwd())

    cleaned = 0
    for project_path in sorted(project_paths):
        local_settings = project_path / ".claude" / "settings.local.json"
        if not local_settings.exists():
            continue
        try:
            settings = read_json(local_settings, {})
        except json.JSONDecodeError:
            _warn(f"Skipping malformed {local_settings}")
            continue

        before = json.dumps(settings)
        _clean_stale_hooks(settings)
        after = json.dumps(settings)

        if before != after:
            write_json(local_settings, settings)
            try:
                label = str(local_settings.relative_to(Path.home()))
            except ValueError:
                label = str(local_settings)
            _ok(f"Cleaned stale hooks in ~/{label}")
            cleaned += 1

    if cleaned:
        _ok(f"Project local settings cleaned: {cleaned} file(s) updated")
    else:
        _skip("No stale hooks in project settings.local.json files")


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
    """Install and start clean-rag, the only RAG server there is now.

    This used to `pip install -e mcp-rag-server`, the port 8612 server. That
    server and its package are removed; clean-rag on 8613 replaced it. It is
    not a package, it runs from source, so this installs its requirements
    rather than the tree itself.
    """
    _info("\nVerifying RAG server...")
    rag_dir = BOOST_HOME / "clean-rag"
    req = rag_dir / "requirements.txt"
    _info(f"Installing clean-rag dependencies from {req}...")
    rc, out = _pip_install(["-r", str(req)])
    if rc != 0:
        _warn(f"pip install returned exit code {rc}")
        if out:
            _warn(out)
        _warn(f"  Run manually: {' '.join(_pip_cmd())} install -r {req}")
    else:
        _ok("clean-rag dependencies installed")

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

    # Pre-download the embedding model so the server can load it offline on first run.
    # Without this, a fresh install hits an empty HF cache and the server (which loads
    # with local_files_only) 500s every /index until the model gets fetched. Warm the
    # cross-encoder reranker too — it's the other model the server needs offline.
    _info("Pre-downloading embedding model (first run only)...")
    _dl = (
        "from sentence_transformers import SentenceTransformer, CrossEncoder; import os; "
        "SentenceTransformer(os.environ.get('RAG_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')); "
        "en = os.environ.get('RAG_RERANKER_ENABLED', '1').strip().lower() not in ('0', 'false', 'off'); "
        "CrossEncoder(os.environ.get('RAG_RERANKER_MODEL', 'cross-encoder/ms-marco-MiniLM-L6-v2')) if en else None; "
        "print('models cached')"
    )
    rc, out = run_cmd([sys.executable, "-c", _dl])
    if rc == 0:
        _ok("Embedding model cached for offline use")
    else:
        _warn("Model pre-download failed — the server will fetch it on first use instead")
        if out:
            _warn(out)

    _info("Installing HTTP server deps (starlette + uvicorn)...")
    rc, out = _pip_install(["starlette>=0.37", "uvicorn[standard]>=0.29"])
    if rc != 0:
        _warn(f"starlette/uvicorn install failed: {out}")
    else:
        _ok("HTTP server deps installed (starlette + uvicorn)")

    # Start it. clean-rag owns its own control CLI, so there is no separate
    # launcher script to keep in sync any more.
    _info("Starting clean-rag (port 8613)...")
    start_script = rag_dir / "cli" / "server_ctl.py"
    rc, out = run_cmd([sys.executable, str(start_script), "start"])
    if rc == 0:
        _ok(f"clean-rag running: {out.splitlines()[-1] if out else 'port 8613'}")
        _prime_rag_session()
        _seed_rag_index()
    else:
        _warn("clean-rag did not start — run it manually:")
        _warn(f"  {sys.executable} \"{start_script}\" start")

    # Clean up any stale MCP registration (idempotent)
    _cleanup_mcp_registration()


# ---------------------------------------------------------------------------
# RAG session prime: write the sentinel file and call /context so session-
# primer.py doesn't block the first prompt after setup.
# ---------------------------------------------------------------------------
def _prime_rag_session() -> None:
    import urllib.request
    import urllib.error

    # Write sentinel — session-primer.py checks for this file before every
    # prompt. Without it, the UserPromptSubmit hook blocks with HARD STOP.
    sentinel = Path(tempfile.gettempdir()) / "claudeboost_rag_ok"
    try:
        sentinel.touch()
        _ok(f"RAG sentinel written: {sentinel}")
    except OSError as e:
        _warn(f"Could not write RAG sentinel ({e}) — run /rag after setup to prime the session")
        return

    # Warm the embedder with a real search. This used to POST /context, an
    # endpoint of the retired 8612 server; clean-rag has no equivalent and
    # never did. A /search does the same job here, which is to force the model
    # load now rather than on the user's first real query.
    #
    # Failures are not fatal: the model may still be downloading, and the
    # server is confirmed running at this point.
    try:
        import json as _json
        body = _json.dumps({
            "query": "session start",
            "sources": [f"project:{BOOST_HOME_POSIX}"],
            "mode": "both",
            "limit": 1,
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8613/search", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            data = _json.loads(r.read())
            hits = len(data.get("results", []))
            _ok(f"RAG session primed ({hits} results)")
    except Exception as e:
        _warn(f"RAG prime failed ({e}) — model may still be loading, run /rag if needed")


# ---------------------------------------------------------------------------
# RAG index seed: index ClaudeBoost knowledge bases after server starts so
# /context and /search work immediately after install without requiring the
# user to run /index-boost or /boost first.
# ---------------------------------------------------------------------------
def _seed_rag_index() -> None:
    import json as _json
    import urllib.error
    import urllib.request

    _info("Indexing ClaudeBoost knowledge bases (agents/ + knowledge/)...")
    try:
        body = _json.dumps({
            "project_path": BOOST_HOME_POSIX,
            "force": False,
        }).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:8613/index-project", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            data = _json.loads(r.read())
            indexed = data.get("files_indexed", 0)
            unchanged = data.get("files_unchanged", 0)
            failed = data.get("files_failed", 0)
            if failed:
                _warn(f"Knowledge bases indexed with errors: {indexed} new, {unchanged} unchanged, {failed} failed")
                _warn("  Run /index-boost in Claude Code to retry failed files")
            else:
                _ok(f"Knowledge bases indexed: {indexed} new, {unchanged} unchanged")
    except Exception as e:
        _warn(f"Knowledge base indexing failed ({e})")
        _warn("  Run /index-boost in Claude Code to index manually")


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
def _claude_cmd() -> list[str] | None:
    """Return a subprocess-safe claude invocation, or None if not found.

    On Windows, `claude` installs as `claude.cmd` which subprocess.run can't
    find without shell=True. We detect the .cmd variant explicitly.
    """
    for candidate in ("claude", "claude.cmd"):
        path = shutil.which(candidate)
        if path:
            # On Windows, .cmd files must be run via cmd.exe
            if candidate.endswith(".cmd"):
                return ["cmd", "/c", path]
            return [path]
    return None


# The debugging surface, one row per server. Everything an agent needs to step
# through code, watch a browser, read coverage, or attach a native debugger is
# registered from this table. Adding a server means adding a row here AND
# enumerating its tool names in the agent frontmatter that should see it —
# Claude Code rejects `mcp__<server>__*` wildcards, so there is no shortcut.
#
# `name` is load-bearing: the tool prefix is derived from it, so changing a
# name here silently breaks every enumerated `mcp__<name>__<tool>` downstream.
MCP_SERVERS: list[dict] = [
    {
        "name": "mcp-debugger",
        "label": "mcp-debugger",
        "args": ["npx", "-y", "@debugmcp/mcp-debugger", "stdio"],
        "needs": "npx",
        "hint": "ensure Node 22+ is installed",
        "why": "step-through debugging: Python, Ruby, Node, Go, Java, .NET, Rust",
    },
    {
        "name": "playwright",
        "label": "Playwright MCP",
        "args": ["npx", "-y", "@playwright/mcp@latest"],
        "needs": "npx",
        "why": "browser automation for browser-agent and /qa",
    },
    {
        "name": "test-coverage",
        "label": "test-coverage MCP",
        "args": ["npx", "-y", "test-coverage-mcp"],
        "needs": "npx",
        "why": "LCOV coverage summaries and diff-since-start for bad-cop",
    },
    {
        "name": "chrome-devtools",
        "label": "Chrome DevTools MCP",
        "args": ["npx", "-y", "chrome-devtools-mcp@latest"],
        "needs": "npx",
        "why": "network capture, performance traces, Lighthouse, Hermes/React Native over CDP",
    },
]


def parse_mcp_list(stdout: str) -> dict[str, str]:
    """Map each server name in `claude mcp list` output to its OWN status text.

    Real output is a header line then one server per line, shaped
    `<name>: <command-or-url> - <status>`:

        Checking MCP server health...

        mcp-debugger: npx -y @debugmcp/mcp-debugger stdio - ✔ Connected
        playwright: npx -y @playwright/mcp@latest - ✗ Failed to connect
        claude.ai GitHub: https://api.githubcopilot.com/mcp - ! Needs authentication

    Names may contain spaces and commands may contain colons (URLs, Windows
    paths), so the name is everything before the FIRST ": " and the status is
    everything after the LAST " - ". Lines without a ": " (the header, blanks)
    are not servers and are dropped.

    Parsing per line is the whole point: a substring test against the joined
    output reports one server's status for another, and reports "mdb" present
    when only an unrelated "cmdb" is registered.
    """
    servers: dict[str, str] = {}
    for line in stdout.splitlines():
        name, sep, rest = line.partition(": ")
        if not sep or not name.strip():
            continue
        _, dash, status = rest.rpartition(" - ")
        servers[name.strip()] = status.strip() if dash else ""
    return servers


def _is_connected(status: str) -> bool:
    """True only for a genuinely connected status, not "Failed to connect"."""
    return re.search(r"\bconnected\b", status, re.IGNORECASE) is not None


def _register_one(claude: list[str], listed: str, server: dict) -> None:
    """Register a single MCP server at user scope. Never fatal.

    Body is the original per-server logic from register_mcp_debugger and
    register_playwright_mcp, with only the name and args parameterized.
    """
    name, label = server["name"], server["label"]
    args = server["args"]

    needs = server.get("needs")
    if needs and not shutil.which(needs):
        _warn(f"{needs} not found — {label} needs it, skipping")
        _warn(f"  To register manually: claude mcp add {name} --scope user -- {' '.join(args)}")
        return

    status = parse_mcp_list(listed).get(name)
    if status is not None:
        if _is_connected(status):
            _ok(f"{label} already registered and connected")
        else:
            hint = server.get("hint", "run /mcp to connect")
            _warn(f"{label} registered but not connected — {hint}")
        return

    _info(f"Registering {label} (user scope)...")
    rc, out = run_cmd(claude + ["mcp", "add", name, "--scope", "user", "--"] + args)
    if rc == 0:
        _ok(f"{label} registered — run /mcp to connect")
    else:
        _warn(f"{label} registration failed (exit {rc})")
        if out:
            _warn(f"  {out[:200]}")
        _warn(f"  To register manually: claude mcp add {name} --scope user -- {' '.join(args)}")


# Note the upstream rename: this was GDB-MCP. Cloning the old name 404s.
MDB_MCP_REPO = "https://github.com/smadi0x86/MDB-MCP.git"


def _clone_mdb_mcp(dest: Path) -> bool:
    """Clone MDB-MCP into `dest`. Self-healing and never leaves partial state.

    `git clone` refuses a destination that exists and is not empty, so an
    interrupted clone used to leave a directory that made every later run fail
    identically, forever, with no way out but deleting it by hand.

    Two changes close that off, following pre-commit's Store._new_repo, which
    clones into a staging directory beside the store, wrapped in
    `clean_path_on_failure`, and only moves it into place once the clone
    worked:
      - any leftover checkout without a server.py is removed first, so an
        already wedged install heals itself on the next run;
      - the clone lands in a staging directory and is moved into place only
        once it really produced server.py, so neither an interruption nor a
        half-finished checkout can leave something at `dest` that later runs
        mistake for a working install.

    The staging path is a fixed sibling rather than pre-commit's
    `tempfile.mkdtemp`, because there is exactly one destination here: a fixed
    name can be swept on the next run, where a random one would litter
    ~/.claude/mcp-servers with an orphan directory per interrupted install.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.parent / ".MDB-MCP-clone"

    for stale, why in ((dest, "incomplete MDB-MCP checkout"),
                       (staging, "leftover MDB-MCP clone staging directory")):
        if not stale.exists():
            continue
        _info(f"Removing {why} before re-cloning...")
        try:
            shutil.rmtree(stale)
        except OSError as e:
            _warn(f"MDB-MCP: could not remove {stale} ({e})")
            _warn("  Delete that directory, then re-run setup to retry.")
            return False

    try:
        _info("Cloning MDB-MCP (native GDB/LLDB debugging)...")
        rc, out = run_cmd(["git", "clone", "--depth", "1", MDB_MCP_REPO, str(staging)])
        if rc != 0 or not (staging / "server.py").exists():
            _warn("MDB-MCP clone failed — native GDB/LLDB debugging unavailable")
            if out:
                _warn(f"  {out[:200]}")
            return False
        try:
            staging.replace(dest)
        except OSError as e:
            _warn(f"MDB-MCP: could not move the clone into {dest} ({e})")
            return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return True


def _mdb_mcp_server() -> list[str] | None:
    """Vendor smadi0x86/MDB-MCP and return its stdio launch args, or None.

    Native GDB/LLDB debugging. Unlike every other row in MCP_SERVERS this is
    not an npx package — it is a Python stdio server that has to be cloned and
    given its deps. Low maintenance signal upstream (small repo, LLDB support
    marked experimental), so every failure path here is a soft skip: a missing
    native debugger must never fail the install.
    """
    if not shutil.which("git"):
        _skip("git not found — skipping MDB-MCP (native GDB/LLDB debugging)")
        return None

    dest = CLAUDE_DIR / "mcp-servers" / "MDB-MCP"
    server_py = dest / "server.py"

    if not server_py.exists() and not _clone_mdb_mcp(dest):
        return None

    rc, _ = run_cmd([sys.executable, "-c", "import mcp, pygdbmi"])
    if rc != 0:
        _info("Installing MDB-MCP dependencies (mcp, pygdbmi)...")
        rc, out = _pip_install(["mcp", "pygdbmi"])
        if rc != 0:
            _warn("MDB-MCP deps failed to install — native GDB/LLDB debugging unavailable")
            if out:
                _warn(f"  {out[:200]}")
            return None

    return [sys.executable, str(server_py)]


def register_mcp_servers() -> None:
    """Register every MCP server in MCP_SERVERS, plus the vendored MDB-MCP.

    Idempotent: `claude mcp list` is read once up front and each server is
    skipped if it is already there. Nothing here is fatal — a missing runtime
    or an offline network degrades the debugging surface, it does not break
    the install.
    """
    _info("\nVerifying MCP servers...")

    claude = _claude_cmd()
    if claude is None:
        _skip("claude CLI not found — skipping MCP server registration")
        return

    rc, listed = run_cmd(claude + ["mcp", "list"])
    if rc != 0:
        _skip(f"claude mcp list failed (exit {rc}) — skipping MCP server registration")
        return

    for server in MCP_SERVERS:
        _register_one(claude, listed, server)

    # Native debugging is opt-in-shaped: it only registers if the clone and the
    # deps both land. Checked last so a failure can't stop the npx servers.
    # Exact name lookup, not `"mdb" in listed` — that matched any server whose
    # name merely contains "mdb" (a "cmdb" server, say) and silently skipped
    # the real registration, leaving every mcp__mdb__* tool orphaned.
    if "mdb" in parse_mcp_list(listed):
        _ok("MDB-MCP already registered")
        return
    args = _mdb_mcp_server()
    if args:
        _register_one(claude, listed, {
            "name": "mdb",
            "label": "MDB-MCP (native GDB/LLDB)",
            "args": args,
            "why": "native C/C++ debugging via GDB and LLDB",
        })


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
# netcoredbg: download from Samsung GitHub releases so mcp-debugger can step
# through .NET/C# code. Skipped when dotnet SDK is not installed.
# ---------------------------------------------------------------------------
def _add_to_user_path(new_dir: str) -> None:
    """Add new_dir to the user's persistent PATH.

    Windows: writes to HKCU\\Environment\\PATH via winreg (no char-limit risk).
    macOS/Linux: appends an export line to ~/.profile.
    No-ops if the directory is already present.
    """
    if IS_WINDOWS:
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
            )
            try:
                current, _ = winreg.QueryValueEx(key, "PATH")
            except FileNotFoundError:
                current = ""
            if new_dir.lower() not in current.lower():
                new_val = f"{current};{new_dir}" if current else new_dir
                winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_val)
                _ok("PATH updated (user registry) — restart terminal for it to take effect")
            winreg.CloseKey(key)
        except Exception as exc:
            _warn(f"Could not update PATH via registry: {exc}")
            _warn(f"  Add manually to your user PATH: {new_dir}")
    else:
        profile = Path.home() / ".profile"
        export_line = f'\nexport PATH="$PATH:{new_dir}"\n'
        try:
            existing = profile.read_text(encoding="utf-8") if profile.exists() else ""
            if new_dir not in existing:
                with profile.open("a", encoding="utf-8") as f:
                    f.write(export_line)
                _ok("PATH updated in ~/.profile — restart terminal for it to take effect")
        except Exception as exc:
            _warn(f"Could not update ~/.profile: {exc}")
            _warn(f'  Add manually: export PATH="$PATH:{new_dir}"')


def install_netcoredbg() -> None:
    """Download netcoredbg from Samsung/netcoredbg GitHub releases.

    Uses only stdlib (urllib, zipfile, tarfile, winreg) — no extra deps.
    Installs to ~/.netcoredbg/ and adds the binary dir to the user PATH.
    """
    import json as _json
    import tarfile
    import urllib.error
    import urllib.request
    import zipfile

    _info("\nVerifying netcoredbg (mcp-debugger .NET support)...")

    if shutil.which("netcoredbg"):
        _ok("netcoredbg already on PATH")
        return

    if not shutil.which("dotnet"):
        _skip("dotnet SDK not found — netcoredbg only needed for .NET debugging")
        return

    # Map platform + arch to the GitHub release asset name.
    mach = platform.machine().lower()
    if mach in ("x86_64", "amd64"):
        arch = "x64"
    elif mach in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        _warn(f"netcoredbg: unsupported architecture {platform.machine()} — install manually "
              "from https://github.com/Samsung/netcoredbg/releases")
        return

    if IS_WINDOWS:
        if arch == "arm64":
            _warn("netcoredbg: no Windows arm64 binary available — skipping .NET debugger install")
            return
        asset_name = "netcoredbg-win64.zip"
    elif IS_MACOS:
        asset_name = f"netcoredbg-osx-{arch}.tar.gz"
    else:
        asset_name = f"netcoredbg-linux-{arch}.tar.gz"

    # Fetch latest release metadata from GitHub.
    _info(f"  Fetching latest netcoredbg release ({asset_name})...")
    api_url = "https://api.github.com/repos/Samsung/netcoredbg/releases/latest"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "ClaudeBoost-setup"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            release = _json.loads(resp.read())
    except Exception as exc:
        _warn(f"netcoredbg: could not fetch release info ({exc})")
        _warn("  Install manually from https://github.com/Samsung/netcoredbg/releases")
        return

    asset_url = next(
        (a["browser_download_url"] for a in release.get("assets", []) if a["name"] == asset_name),
        None,
    )
    if not asset_url:
        _warn(f"netcoredbg: asset {asset_name!r} not in release {release.get('tag_name', '?')}")
        _warn("  Install manually from https://github.com/Samsung/netcoredbg/releases")
        return

    install_dir = Path.home() / ".netcoredbg"
    install_dir.mkdir(exist_ok=True)
    tmp_path = install_dir / asset_name

    _info(f"  Downloading {release.get('tag_name', 'latest')} ...")
    try:
        urllib.request.urlretrieve(asset_url, tmp_path)
    except Exception as exc:
        _warn(f"netcoredbg: download failed ({exc})")
        return

    _info("  Extracting...")
    try:
        if asset_name.endswith(".zip"):
            with zipfile.ZipFile(tmp_path) as zf:
                zf.extractall(install_dir)
        else:
            with tarfile.open(tmp_path) as tf:
                tf.extractall(install_dir)
        tmp_path.unlink(missing_ok=True)
    except Exception as exc:
        _warn(f"netcoredbg: extraction failed ({exc})")
        return

    exe_name = "netcoredbg.exe" if IS_WINDOWS else "netcoredbg"
    candidates = list(install_dir.rglob(exe_name))
    if not candidates:
        _warn(f"netcoredbg: binary {exe_name!r} not found after extraction")
        return
    bin_path = candidates[0]
    if not IS_WINDOWS:
        bin_path.chmod(bin_path.stat().st_mode | 0o755)

    _add_to_user_path(str(bin_path.parent))

    rc, out = run_cmd([str(bin_path), "--version"])
    if rc == 0:
        _ok(f"netcoredbg installed: {out.strip()}")
    else:
        _ok(f"netcoredbg installed at {bin_path}")
        _warn("  Restart your terminal for the PATH change to take effect, then verify with: netcoredbg --version")


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
    _clean_project_local_settings()
    install_rag_server()
    register_mcp_servers()
    install_edge_tts()
    install_netcoredbg()
    install_clean_rag()

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
