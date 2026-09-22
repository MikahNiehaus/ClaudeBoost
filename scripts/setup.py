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
import sysconfig
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Sibling module. setup.py always runs out of the repo's own scripts/ dir
# (install.sh calls "$BOOST_DIR/scripts/setup.py"), so the helper is next to it.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_cli import claude_cmd  # noqa: E402

# Windows consoles default to cp1252. run_cmd decodes child output as UTF-8,
# and relaying it (the ollama pull spinner emits braille) raised
# UnicodeEncodeError from install_clean_rag, which killed the two install
# steps after it. Same idiom as prompt-rules-injector.py.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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

#: The floor every hook must load under. Hooks are plain scripts run by
#: whichever interpreter the hook command line resolves, so a syntax or
#: annotation feature newer than this breaks them at import time, above their
#: own fail open handlers, and every Edit in the session emits a traceback.
#: Named here rather than spelled into each message so the check and the label
#: the user reads cannot drift apart.
MIN_PYTHON = (3, 9)
MIN_PYTHON_STR = "{}.{}".format(*MIN_PYTHON)


def _interpreter_version(exe: str):
    """(major, minor) that `exe` reports, or None if it will not tell us.

    None covers a missing binary, a Windows Store alias stub, and anything that
    prints something unparseable. All of those read as "cannot confirm", which
    the callers treat as no finding rather than as a failure.
    """
    try:
        proc = subprocess.run(
            [exe, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None
    parts = proc.stdout.strip().split(".")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _check_python() -> bool:
    """Confirm the interpreters that will actually run the hooks meet the floor.

    hook_command() tries $CLAUDEBOOST_PYTHON first, then python3, python, py.
    write_env() points $CLAUDEBOOST_PYTHON at the interpreter running this
    script, so that one is required to meet the floor and setup refuses without
    it: installing hooks that cannot load is worse than not installing them,
    because the failure surfaces as a traceback on every Edit with nothing
    naming the cause.

    A PATH fallback below the floor only bites when the env var is missing from
    the shell, so it warns and lets the install continue.
    """
    running = sys.version_info[:2]
    label = "Python {}+".format(MIN_PYTHON_STR)
    if running < MIN_PYTHON:
        _err(
            "{} required. Setup is running under Python {}.{} ({}). "
            "Hooks installed by this interpreter would fail to load. "
            "Re-run setup with Python {} or newer.".format(
                label, running[0], running[1], sys.executable, MIN_PYTHON_STR)
        )
        return False
    _ok("{} (running {}.{})".format(label, running[0], running[1]))

    for name in ("python3", "python", "py"):
        path = shutil.which(name)
        if not path:
            continue
        found = _interpreter_version(path)
        if found is not None and found < MIN_PYTHON:
            _warn(
                "`{}` on PATH is Python {}.{}, below {}. Hooks fall back to it "
                "only when $CLAUDEBOOST_PYTHON is unset in the shell, and would "
                "not load if they did.".format(
                    name, found[0], found[1], MIN_PYTHON_STR)
            )
    return True


def preflight() -> bool:
    _info("Running preflight checks...")
    ok = _check_python()
    # pip is checked via `python -m pip` instead of a bare `pip` binary,
    # since macOS commonly ships Python without exposing `pip` on PATH.
    requirements = [
        ("pip",    "pip",          True, lambda: subprocess.run([sys.executable, "-m", "pip", "--version"],
                                                                capture_output=True).returncode == 0),
        ("claude", "Claude Code CLI", True, lambda: bool(shutil.which("claude"))),
        ("git",    "Git",          False, lambda: bool(shutil.which("git"))),
    ]
    for cmd, label, required, check in requirements:
        if check():
            _ok(label)
        elif required:
            _err(f"{label} not found. Install it before re-running setup.")
            ok = False
        else:
            _warn(f"{label} not found. Some features may not work.")
    return ok


# ---------------------------------------------------------------------------
# MCP cleanup: remove rag-server from mcp.json if it was registered by an
# older version of setup. The RAG server is now a standalone HTTP daemon on
# port 8613 — no MCP registration needed or wanted.
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
# Lives in ~/.claude/, deliberately outside the repo: a checkout cannot remove
# it, so it still answers for a branch that predates the hook pointing at it.
# clean-rag/install.py defines the same path for the same reason; the two must
# agree or a hook wrapped by one looks unwrapped to the other.
HOOK_RUNNER = Path.home() / ".claude" / "hook-run.py"


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


def _py_cmd(script_name: str, base_dir: str = "scripts",
            runner: str | None = None) -> str:
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

    Each branch launches through hook-run.py rather than the script directly, so
    a branch switch that removes the script exits 0 instead of 2 (Claude Code
    reads 2 from a PreToolUse hook as "block this tool call"). The runner goes
    inside every branch because every branch runs its own interpreter. It is
    emitted here, at the one place that knows the script path, rather than
    spliced in afterwards by parsing this finished string: that post-hoc parse
    read the leading `if` as the interpreter and corrupted 29 registrations.
    """
    if runner is None:
        runner = str(HOOK_RUNNER).replace("\\", "/")
    script = f'"$CLAUDEBOOST_HOME/{base_dir}/{script_name}"'
    launch = f'"{runner}" {script}'
    return (
        f'if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then "$CLAUDEBOOST_PYTHON" {launch}; '
        f'elif command -v python3 >/dev/null 2>&1; then python3 {launch}; '
        f'elif command -v python >/dev/null 2>&1; then python {launch}; '
        f'else py {launch}; fi'
    )


def _hook_command_stale(cmd: str) -> bool:
    """Stale = references an absolute script path that no longer exists.

    Commands using env-var refs ($CLAUDEBOOST_PYTHON, $CLAUDEBOOST_HOME, $HOME,
    %APPDATA%, etc.) are portable and left alone — can't verify statically, and
    they're intentionally written that way.
    """
    import re
    # Skip the hook-run.py wrapper. It is an absolute path that always exists,
    # and it now sits in front of the real script, so matching the first .py
    # would answer "not stale" for every command regardless of its target.
    candidates = [c for c in re.findall(r'"([^"]+\.py)"', cmd)
                  if "hook-run.py" not in c]
    if candidates:
        candidate = candidates[0]
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
    # Dropped 2026-09-10. Claude Code rejects every prompt-type SessionStart
    # hook outright: "prompt-type hooks are not supported for SessionStart
    # events (no conversation context is available)." All three duplicated
    # content that ~/.claude/CLAUDE.md already loads every session, and the RAG
    # block is re-injected by the UserPromptSubmit hook on every turn.
    #
    # These three match on statusMessage, not prompt text, on purpose. The
    # installed prompt text has already drifted from what this file writes: a
    # later plain-writing pass rewrote "Quality-first routing" to "Quality
    # first routing", the sentinel in _install_hook stopped matching, and the
    # next setup run appended a SECOND copy of the same hook. statusMessage is
    # the field that stayed identical across both copies.
    "Loading ClaudeBoost workflow...",      # workflow routing (installed twice)
    "Loading CONSULT mode protocol...",     # CONSULT vs AUTO protocol
    "Loading RAG HTTP API config...",       # RAG HTTP API contract
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
                # Match on prompt text AND statusMessage, but only for
                # prompt-type hooks. Prompt text drifts when someone rewrites
                # the wording; statusMessage does not. Restricting to
                # prompt-type keeps a command hook that happens to share a
                # statusMessage from being swept up, which the old
                # prompt-text-only read guaranteed for free.
                is_prompt = isinstance(h, dict) and (
                    h.get("type") == "prompt" or ("type" not in h and "prompt" in h)
                )
                text = ""
                if is_prompt:
                    text = (h.get("prompt", "") or "") + "\n" + (h.get("statusMessage", "") or "")
                if text.strip() and any(s in text for s in _SUPERSEDED_PROMPT_SENTINELS):
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
    "lt-precompact.py",   # Low Token Mode dropped 2026-08-23; PreCompact hook
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
                elif "matcher" not in entry and "matcher" in e:
                    # The caller dropped the matcher, so the installed one is
                    # stale and must go. Without this branch the refresh above
                    # only ever handles a CHANGED value, never a REMOVED key,
                    # and a wrong matcher survives every future setup run.
                    # That is how "matcher": "Always" outlived its own removal
                    # from this file and silently killed every SessionStart
                    # hook it was attached to.
                    del e["matcher"]
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


# ---------------------------------------------------------------------------
# Terminal mode reset: recover the shell after Claude Code is killed rather
# than exited. See scripts/install-terminal-mode-reset.py for the upstream bug
# (anthropics/claude-code#59720) and why the recovery has to live in the
# PowerShell prompt function.
# ---------------------------------------------------------------------------
def install_terminal_mode_reset() -> None:
    """Wire the terminal mode reset into the user's PowerShell profile.

    Windows only — the block is PowerShell and the recovery it performs is for
    a shell left in xterm mouse-tracking mode, which is the Windows Terminal
    symptom. The installer is marker guarded and append only, backs the profile
    up first, and re-running it is a no op, so it is safe on every setup run.

    This does edit a file outside the repo. So do the netcoredbg PATH entry
    (registry on Windows, ~/.profile elsewhere) and the logon scheduled task,
    and uninstall.py reverses all three.
    """
    if not IS_WINDOWS:
        _skip("terminal mode reset - Windows only")
        return

    installer = BOOST_HOME / "scripts" / "install-terminal-mode-reset.py"
    if not installer.is_file():
        _skip(f"terminal mode reset - {installer.name} not present")
        return

    code, out = run_cmd([sys.executable, str(installer)])
    if out:
        for line in out.splitlines():
            print(f"    {line}")
    if code == 0:
        _ok("terminal mode reset wired into the PowerShell profile")
    else:
        _warn(f"terminal mode reset installer exited {code} — profile left unchanged")


# Hook prompts are kept verbatim from setup.ps1 — sentinels must match so
# re-running this script never duplicates an entry that the PowerShell
# version installed previously.
def _install_all_hooks(settings: dict) -> None:
    _info("\nCleaning up stale hooks...")
    _clean_stale_hooks(settings)
    _remove_superseded_hooks(settings)
    _remove_deleted_script_hooks(settings)

    # SessionStart prompt-type hooks removed 2026-09-10. There were three:
    # workflow routing, the CONSULT vs AUTO protocol, and the RAG HTTP API
    # contract. Claude Code refuses to run any of them and says so:
    #     Failed to run: prompt-type hooks are not supported for SessionStart
    #     events (no conversation context is available). Use a command-type
    #     hook instead.
    # Every one of them duplicated content ~/.claude/CLAUDE.md already loads
    # on every session, and the RAG block is re-injected by the
    # UserPromptSubmit hook on every single turn, so nothing was lost.
    # _SUPERSEDED_PROMPT_SENTINELS strips them from installs that already have
    # them. If you want context injected at session start, write a command-type
    # hook that prints {"additionalContext": "..."} on stdout, the way
    # reindex-check.py does. Do not re-add a prompt-type hook here.


    # --- SessionStart: compaction restore ---
    _install_hook(settings, "SessionStart", {
        "hooks": [{
            "type": "command",
            "command": _py_cmd("compaction-restore.py"),
            "timeout": 5000,
            "statusMessage": "Restoring context after compaction...",
        }],
    }, sentinel="compaction-restore.py", label="compaction restore (command-type)")

    # --- SessionStart: workspace primer ---
    _install_hook(settings, "SessionStart", {
        "hooks": [{
            "type": "command",
            "command": _py_cmd("workspace-primer.py"),
            "timeout": 5000,
            "statusMessage": "Loading workspace tier briefing...",
        }],
    }, sentinel="workspace-primer.py", label="workspace tier primer (command-type)")

    # The memory watcher is deliberately NOT registered here. It was, for one
    # session on 2026-08-24, and it made the machine unusable: SessionStart
    # fires on every session start, Claude Code was restarting repeatedly at
    # the time, and each firing put a visible Python console on screen. The
    # launcher asked for CREATE_NO_WINDOW and DETACHED_PROCESS together, which
    # are contradictory on Windows, so the window was never reliably
    # suppressed. Start it by hand instead:
    #     python scripts/memory-watcher.py
    # Before wiring it to a hook again, fix the creationflags and prove no
    # window appears across a real session start, not just a manual run.

    # --- SessionStart: RAG session reset (clears sentinel for fresh session verification) ---
    _install_hook(settings, "SessionStart", {
        "hooks": [{
            "type": "command",
            "command": _py_cmd("rag-session-reset.py"),
            "timeout": 3000,
            "statusMessage": "Resetting RAG sentinel for fresh session verification...",
        }],
    }, sentinel="rag-session-reset.py", label="RAG session reset (command-type)")

    # --- PreToolUse: agent-spawn gate on Task (command-type) ---
    # Lives under clean-rag/hooks/, but enforces
    # core ClaudeBoost RAG (port 8613) — installed unconditionally here, not
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
                       "1. Call POST http://127.0.0.1:8613/search with "
                       "{\"query\":\"<task description>\",\"sources\":[\"project:<abs path>\"],\"mode\":\"both\"} "
                       "to find relevant knowledge\n"
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
        "hooks": [
            {
                "type": "prompt",
                "prompt": ("CONTEXT PRESERVATION — quality-first routing:\n"
                           "1. Agent spawns: call POST http://127.0.0.1:8613/search with "
                           "{\"query\":\"...\",\"sources\":[\"project:<abs path>\"],\"mode\":\"both\"}, "
                           "route by type (full/standard/lightweight)\n"
                           "2. Finding verification: ALWAYS quick-cop, never self-verify "
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

    # Low Token Mode was removed on 2026-08-23. It opened a new Windows
    # Terminal tab when context filled and killed the current one. The launcher
    # hardcoded `pwsh`, which is not installed by default on Windows, so every
    # compaction raised "error 2147942402 ... cannot find the file specified"
    # and no new tab appeared. /clear-safe covers the same need and is kept.

    # --- SessionEnd: clear handoff save ---
    _install_hook(settings, "SessionEnd", {
        "hooks": [{"type": "command", "command": _py_cmd("session-clear-save.py")}],
    }, sentinel="session-clear-save.py", label="clear handoff save")

    # --- Telemetry: session lifecycle (SessionStart creates session.json, SessionEnd closes it) ---
    _install_hook(settings, "SessionStart", {
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

    # --- Session restore ledger: records what is open so a reboot can reopen it ---
    # SessionStart adds the session, SessionEnd removes it. A reboot never
    # delivers SessionEnd, so whatever is still listed is what was open.
    _install_hook(settings, "SessionStart", {
        "hooks": [{"type": "command", "command": _py_cmd("session-restore-ledger.py"),
                   "timeout": 3000,
                   "statusMessage": "Recording session for restore..."}],
    }, sentinel="session-restore-ledger.py", label="session restore ledger (start)")

    _install_hook(settings, "SessionEnd", {
        "hooks": [{"type": "command", "command": _py_cmd("session-restore-ledger.py"),
                   "timeout": 3000}],
    }, sentinel="session-restore-ledger.py", label="session restore ledger (end)")



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

    # pipe-down ships a 25 word cap and an LLM judge that spawns a claude
    # subprocess per write. setdefault, not assignment, so a human who retunes
    # either one keeps their value across re-runs.
    env.setdefault("PIPE_DOWN_MAX_WORDS", "20")
    env.setdefault("PIPE_DOWN_LLM", "0")

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
            encoding="utf-8", errors="replace",
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

    # The `[graph]` (graspologic) and `[scip]` extras used to be installed here
    # with `pip install -e clean-rag[...]`. clean-rag has no pyproject.toml and
    # imports neither package, so both steps failed on every run and printed a
    # warning for a feature that does not exist. Removed.

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
# RAG session prime: write the sentinel file and run a real /search so
# session-primer.py doesn't block the first prompt after setup.
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
# /search works immediately after install without requiring the user to run
# /index-boost or /boost first.
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
# older setup. The RAG server is now accessed entirely via HTTP on port 8613.
# ---------------------------------------------------------------------------
def _cleanup_mcp_registration() -> None:
    """Remove the rag-server MCP registration if it still exists.

    Idempotent — safe to run multiple times. The RAG server no longer uses MCP;
    it runs as a standalone HTTP daemon on port 8613.
    """
    claude = claude_cmd()
    if claude is None:
        _skip("claude CLI not found — skipping MCP cleanup")
        return

    # Try `claude mcp list` to see current configs
    rc, out = run_cmd(claude + ["mcp", "list"])
    if rc != 0:
        _skip("claude CLI would not run — skipping MCP cleanup")
        return

    if "rag-server" not in out:
        _skip("MCP config - rag-server not registered, nothing to remove")
        return

    # Remove the rag-server entry (try with scope flag first)
    rc_rm, _ = run_cmd(claude + ["mcp", "remove", "rag-server", "--scope", "user"])
    if rc_rm != 0:
        rc_rm, _ = run_cmd(claude + ["mcp", "remove", "rag-server"])
    if rc_rm == 0:
        _ok("MCP config - removed stale rag-server entry (RAG is HTTP-only now)")
    else:
        _warn("Could not remove rag-server from MCP config — remove it manually: "
              "claude mcp remove rag-server")


# ---------------------------------------------------------------------------
# mcp-debugger: register with `claude mcp` at user scope so it's available
# in every Claude session. Idempotent — skips if already registered.
# ---------------------------------------------------------------------------
# The debugging surface, one row per server. Everything an agent needs to step
# through code, watch a browser, read coverage, or attach a native debugger is
# registered from this table. Adding a server means adding a row here AND
# enumerating its tool names in the agent frontmatter that should see it —
# Claude Code rejects `mcp__<server>__*` wildcards, so there is no shortcut.
#
# `name` is load-bearing: the tool prefix is derived from it, so changing a
# name here silently breaks every enumerated `mcp__<name>__<tool>` downstream.

# Astral's own standalone installer, the one uv's docs lead with. Printed as a
# hint only. The installer never runs it: piping a remote script into a shell
# is a code execution path an installer should not open on the user's behalf.
UV_HINT = ('install uv: "powershell -ExecutionPolicy ByPass -c '
           '\\"irm https://astral.sh/uv/install.ps1 | iex\\"" on Windows, '
           '"curl -LsSf https://astral.sh/uv/install.sh | sh" elsewhere')

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
    # --- Code intelligence -------------------------------------------------
    {
        "name": "serena",
        "label": "Serena (LSP symbol tools)",
        "args": ["uvx", "--from", "git+https://github.com/oraios/serena",
                 "serena", "start-mcp-server"],
        "needs": "uvx",
        "hint": UV_HINT,
        "why": "real symbol references, call hierarchy and rename via language servers",
    },
    {
        "name": "ast-grep",
        "label": "ast-grep MCP",
        "args": ["uvx", "ast-grep-mcp"],
        "needs": "uvx",
        "hint": UV_HINT,
        "why": "structural AST search and codemod rule testing, 4 tools",
    },
    {
        "name": "context7",
        "label": "Context7 (library docs)",
        "args": ["npx", "-y", "@upstash/context7-mcp"],
        "needs": "npx",
        "why": "version pinned library docs, the fix for a stale API guess",
    },
    # --- Security ----------------------------------------------------------
    {
        "name": "semgrep",
        "label": "Semgrep MCP",
        # uvx semgrep-mcp is what semgrep/mcp's own README prescribes, and its
        # example config is literally {"command": "uvx", "args": ["semgrep-mcp"]}.
        # The earlier ["semgrep", "mcp", "-t", "stdio"] needed a working semgrep
        # on PATH; a pip installed one shells out to pysemgrep and dies with
        # "No such file or directory" when the Scripts dir is off PATH. Going
        # through uvx also drops a prerequisite, since four other rows need it.
        "args": ["uvx", "semgrep-mcp"],
        "needs": "uvx",
        "hint": UV_HINT,
        "why": "real SAST, 5000+ rules, scans stay local unless a token is set",
    },
    {
        "name": "osv",
        "label": "OSV vulnerability scanner",
        "args": ["osv-scanner", "mcp"],
        "needs": "osv-scanner",
        "hint": "go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest",
        "why": "citable CVE and advisory IDs across every package ecosystem",
    },
    # --- Research and swipe provenance -------------------------------------
    {
        "name": "arxiv",
        "label": "arXiv MCP",
        "args": ["uvx", "arxiv-mcp-server"],
        "needs": "uvx",
        "hint": UV_HINT,
        "why": "real paper sections and BibTeX; researcher has no WebFetch",
    },
    {
        "name": "socket",
        "label": "Socket (supply chain)",
        "transport": "http",
        "url": "https://mcp.socket.dev/",
        "args": [],
        "why": "score a package before swiper takes it: license, malware, maintenance",
    },
    # --- Explaining and proof ----------------------------------------------
    {
        "name": "antv-chart",
        "label": "AntV chart renderer",
        "args": ["npx", "-y", "@antv/mcp-server-chart"],
        "needs": "npx",
        "why": "PNG mind maps, flowcharts, network graphs, fishbone diagrams",
    },
    {
        "name": "jupyter",
        "label": "Jupyter MCP",
        "args": ["uvx", "jupyter-mcp-server@latest"],
        "needs": "uvx",
        "needs_env": "JUPYTER_TOKEN",
        "hint": "start a Jupyter server and set JUPYTER_TOKEN",
        "why": "executable .ipynb evidence: code, narrative and output a human re-runs",
    },
    # --- Remote, OAuth or token --------------------------------------------
    {
        "name": "github",
        "label": "GitHub MCP",
        "transport": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        # Deliberately NOT GITHUB_TOKEN. That one is clean-rag's, documented as
        # a read only public repo PAT for search. This server needs write scope
        # for PRs and issues, so sharing the name would either break the server
        # or quietly widen what the search token can do.
        "headers": {"Authorization": "Bearer ${GITHUB_MCP_TOKEN}"},
        "args": [],
        "needs_env": "GITHUB_MCP_TOKEN",
        "hint": "needs Copilot enrolment (Copilot Free is $0) on the hosted endpoint",
        "why": "PRs, issues and Actions as structured calls instead of parsing gh output",
    },
    {
        "name": "atlassian",
        "label": "Atlassian MCP",
        "transport": "http",
        "url": "https://mcp.atlassian.com/v1/mcp",
        "args": [],
        "hint": "an org admin must enable Rovo; run /mcp to complete OAuth",
        "why": "live Jira and Confluence read/write for ticket handoff",
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


def _server_json(server: dict) -> str:
    """The `claude mcp add-json` payload for one server row.

    add-json rather than `claude mcp add --env K=V`, because --env is variadic
    and greedily eats whatever follows it, including the server name when the
    two are adjacent (anthropics/claude-code#29221). A JSON object has no
    positional ambiguity, so the footgun cannot fire.

    A credential is emitted as the literal `${VAR}` placeholder, which Claude
    Code expands from the environment at launch. The token therefore never
    lands in ~/.claude.json. The cost is that expansion fails soft: an unset
    var leaves the literal text in place rather than erroring, which is why
    `needs_env` is checked at install time instead of relying on this.
    """
    if server.get("transport") == "http":
        payload: dict[str, Any] = {"type": "http", "url": server["url"]}
        if server.get("headers"):
            payload["headers"] = server["headers"]
    else:
        args = server["args"]
        payload = {"type": "stdio", "command": args[0], "args": args[1:]}
        if server.get("env"):
            payload["env"] = server["env"]
    return json.dumps(payload)


def _manual_hint(server: dict) -> str:
    """The copy-pasteable command to register this server by hand."""
    name = server["name"]
    if server.get("transport") == "http" or server.get("env"):
        return f"claude mcp add-json {name} --scope user '{_server_json(server)}'"
    return f"claude mcp add {name} --scope user -- {' '.join(server['args'])}"


def _script_dirs() -> list[str]:
    """The running interpreter's own console-script directories."""
    dirs = []
    for key in ("scripts", os.name + "_user"):
        try:
            path = (sysconfig.get_path("scripts") if key == "scripts"
                    else sysconfig.get_path("scripts", key))
        except (KeyError, ValueError):
            continue
        if path and os.path.isdir(path) and path not in dirs:
            dirs.append(path)
    return dirs


def resolve_tool(name: str) -> str | None:
    """Absolute path to an executable, or None if it genuinely is not here.

    PATH first, then the interpreter's script directories. `pip install uv`
    drops uv.exe and uvx.exe into a per-user Scripts dir that is not on PATH
    on a default Windows install, so shutil.which alone reports a tool missing
    that is sitting right there. sysconfig derives those directories from the
    running interpreter, so this stays correct under a different user, a venv,
    or another OS, with no path literal anywhere.
    """
    found = shutil.which(name)
    if found:
        return found
    for directory in _script_dirs():
        found = shutil.which(name, path=directory)
        if found:
            return found
    return None


# The four outcomes for one row. Kept as a pure function, byte-identical to the
# copy in clean-rag/install.py, because the two installers previously made this
# decision in hand-written control flow that had already drifted: setup.py
# checked prerequisites first, install.py checked "already registered" first,
# so the same machine got two different answers for the same server.
# tests/test_mcp_server_registration.py drives both copies over a scenario
# matrix, which is what makes a future divergence fail a test instead of
# silently shipping.
#
# Order is the contract, not an accident. A missing prerequisite or credential
# is reported even when the server is already registered, because Claude Code
# expands ${VAR} from its own environment when it launches: a registered row
# whose credential is unset still sends the literal "${VAR}" as the token and
# fails at runtime. Answering "already registered" would hide exactly that.
def registration_action(server: dict, status: str | None, resolve, environ) -> tuple[str, str | None]:
    needs = server.get("needs")
    if needs and not resolve(needs):
        return "skip-missing-tool", needs
    needs_env = server.get("needs_env")
    if needs_env and not environ.get(needs_env):
        return "skip-missing-credential", needs_env
    if status is not None:
        return "already-registered", status
    return "register", None


# Where a credential has to live to actually reach an MCP server. Claude Code
# expands ${VAR} from its own process environment, and clean-rag/.env is read
# by clean-rag's server process only, never by Claude Code. Naming .env here
# would send people to a file that cannot work for this.
CREDENTIAL_HOMES = (
    "set it as a real environment variable for the shell that launches Claude "
    "Code, or add it to the \"env\" block of ~/.claude/settings.json"
)


def _register_one(claude: list[str], listed: str, server: dict) -> None:
    """Register a single MCP server at user scope. Never fatal.

    Body is the original per-server logic from register_mcp_debugger and
    register_playwright_mcp, with only the name and args parameterized.
    """
    name, label = server["name"], server["label"]

    status = parse_mcp_list(listed).get(name)
    action, detail = registration_action(server, status, resolve_tool, os.environ)

    if action == "skip-missing-tool":
        _warn(f"{detail} not found — {label} needs it, skipping")
        if server.get("hint"):
            _warn(f"  {server['hint']}")
        _warn(f"  To register manually: {_manual_hint(server)}")
        return

    if action == "skip-missing-credential":
        _warn(f"{detail} is not set — {label} needs it, skipping")
        _warn(f"  {CREDENTIAL_HOMES}, then re-run setup")
        return

    if action == "already-registered":
        if _is_connected(status):
            _ok(f"{label} already registered and connected")
        else:
            hint = server.get("hint", "run /mcp to connect")
            _warn(f"{label} registered but not connected — {hint}")
        return

    _info(f"Registering {label} (user scope)...")
    if server.get("transport") == "http" or server.get("env"):
        cmd = claude + ["mcp", "add-json", name, "--scope", "user", _server_json(server)]
    else:
        cmd = claude + ["mcp", "add", name, "--scope", "user", "--"] + server["args"]
    rc, out = run_cmd(cmd)
    if rc == 0:
        # "registered", never "working". `claude mcp add` only writes config;
        # it does not start the server. An npx or uvx row that has to download
        # its package on first run routinely exceeds Claude Code's 30s connect
        # timeout, so a zero exit here is consistent with a server that never
        # connects. /mcp is where that actually gets settled.
        _ok(f"{label} registered — run /mcp to confirm it connects")
    else:
        _warn(f"{label} registration failed (exit {rc})")
        if out:
            _warn(f"  {out[:200]}")
        _warn(f"  To register manually: {_manual_hint(server)}")


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

    claude = claude_cmd()
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
# Claude Code plugins. One row per plugin. `marketplace` is what
# `claude plugin marketplace add` takes, `name` is the plugin@marketplace id
# `claude plugin install` takes. Both steps are needed; the marketplace alone
# registers nothing.
# ---------------------------------------------------------------------------
PLUGINS = [
    {
        "name": "ponytail@ponytail",
        "marketplace": "DietrichGebert/ponytail",
        "why": "stops the agent over-building; MIT",
        "needs_node": True,
    },
    # PreToolUse, so an over-long comment is refused rather than written and
    # then nudged. Python, no node needed. Its LLM judge is on by default and
    # spawns a claude subprocess per write, so PIPE_DOWN_LLM is set to 0 below.
    {
        "name": "pipe-down@claude-pipe-down",
        "marketplace": "hoo29/claude-pipe-down",
        "why": "blocks low value and over-long comments before the write; MIT",
    },
]


def install_plugins() -> None:
    """Install every plugin in PLUGINS.

    Idempotent: `claude plugin list` is read once and anything already there is
    skipped. Nothing here is fatal, same as MCP registration. A plugin's hooks
    run as the user on every prompt, so each row is a trust decision, not a
    convenience.
    """
    if not PLUGINS:
        return

    _info("\nVerifying Claude Code plugins...")

    claude = claude_cmd()
    if claude is None:
        _skip("claude CLI not found - skipping plugin install")
        return

    rc, listed = run_cmd(claude + ["plugin", "list"])
    if rc != 0:
        _skip(f"claude plugin list failed (exit {rc}) - skipping plugin install")
        return

    for plugin in PLUGINS:
        name = plugin["name"]
        if name in listed:
            _ok(f"{name} already installed")
            continue

        # Its lifecycle hooks are Node. Without node they fail on every prompt.
        if plugin.get("needs_node") and resolve_tool("node") is None:
            _warn(f"{name} needs node on PATH - skipping")
            continue

        rc, out = run_cmd(claude + ["plugin", "marketplace", "add", plugin["marketplace"]])
        if rc != 0:
            _warn(f"could not add marketplace {plugin['marketplace']} (exit {rc})")
            if out:
                _warn(out.strip()[:300])
            continue

        rc, out = run_cmd(claude + ["plugin", "install", name])
        if rc == 0:
            _ok(f"{name} installed - {plugin['why']}")
        else:
            _warn(f"{name} install failed (exit {rc}); run: claude plugin install {name}")
            if out:
                _warn(out.strip()[:300])


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


def install_mermaid_cli() -> None:
    """Install @mermaid-js/mermaid-cli globally so `mmdc` can render diagrams.

    Gives /visualize and any diagram work a real renderer instead of handing the
    user raw mermaid source. Non-fatal: npm missing or the install failing leaves
    everything else working, so this warns and moves on rather than aborting
    setup.

    The install pulls a bundled Chromium (~180MB, about a minute), so it is
    skipped when `mmdc` already resolves.

    Both probes go through shutil.which first, and that is load bearing on
    Windows, not defensive noise. npm installs `mmdc` as `mmdc.CMD`, and
    subprocess without a shell cannot launch a .CMD by bare name: it raises
    WinError 2, run_cmd turns that into 127, and the already-installed branch
    never fires. The visible symptom is setup redownloading a bundled Chromium
    on every single run. shutil.which honours PATHEXT and returns the real
    mmdc.CMD path, which subprocess can execute.
    """
    _info("\nVerifying mermaid-cli (mmdc)...")
    mmdc = shutil.which("mmdc")
    if mmdc:
        rc, out = run_cmd([mmdc, "--version"])
        if rc == 0 and out.strip():
            _ok(f"mermaid-cli already installed (mmdc {out.strip().splitlines()[0]})")
            return

    if not shutil.which("npm"):
        _warn("npm not found - skipping mermaid-cli. Diagram rendering will be "
              "unavailable until you install Node.js and run: "
              "npm install -g @mermaid-js/mermaid-cli")
        return

    _info("Installing mermaid-cli (downloads a bundled Chromium, ~1 min)...")
    npm = shutil.which("npm") or "npm"
    rc, out = run_cmd([npm, "install", "-g", "@mermaid-js/mermaid-cli"])
    if rc != 0:
        _warn("mermaid-cli install failed - diagram rendering will not work "
              "until you run: npm install -g @mermaid-js/mermaid-cli")
        if out:
            _warn(out[-800:])
        return

    # npm exiting 0 is not proof the binary resolves: a global bin dir missing
    # from PATH is the common Windows case, and it fails silently at use time.
    mmdc = shutil.which("mmdc")
    rc, out = run_cmd([mmdc, "--version"]) if mmdc else (127, "")
    if rc == 0 and out.strip():
        _ok(f"mermaid-cli installed (mmdc {out.strip().splitlines()[0]})")
    else:
        _warn("mermaid-cli installed but `mmdc` is not on PATH. Add npm's global "
              "bin directory to PATH (`npm bin -g`) and restart your terminal.")


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
# Session restore: the at logon trigger
#
# The only OS level autostart ClaudeBoost registers. Everything else self heals
# from a hook inside an already running session, which cannot work here because
# the whole point is that nothing is running yet after a reboot.
#
# Set CLAUDEBOOST_NO_SESSION_RESTORE_TASK=1 to skip it. uninstall.py removes it.
# ---------------------------------------------------------------------------
def install_session_restore_task() -> None:
    _info("\nRegistering session restore at logon...")

    if os.environ.get("CLAUDEBOOST_NO_SESSION_RESTORE_TASK"):
        _skip("session restore task (CLAUDEBOOST_NO_SESSION_RESTORE_TASK is set)")
        return

    if not IS_WINDOWS:
        _skip("session restore at logon is Windows only "
              "(the ledger and manual restore still work everywhere)")
        return

    script = BOOST_HOME / "scripts" / "session-restore.py"
    if not script.exists():
        _warn(f"session-restore.py missing at {script}, skipping the logon task")
        return

    rc, out = run_cmd([sys.executable, str(script), "--install-task"])
    for line in (out or "").splitlines():
        if line.strip():
            print(f"  {line.rstrip()}")
    if rc != 0:
        _warn("session restore task not registered, run /restore-sessions by hand after a reboot")


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
    install_plugins()
    install_edge_tts()
    install_mermaid_cli()
    install_netcoredbg()
    install_clean_rag()
    install_terminal_mode_reset()
    install_session_restore_task()

    _info("\n=== Setup Complete ===")
    print(f"  CLAUDEBOOST_HOME = {BOOST_HOME_POSIX}")
    print( "  RAG HTTP server started on port 8613")
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
