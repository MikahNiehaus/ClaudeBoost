"""ClaudeBoost uninstaller, cross-platform (Windows, macOS, Linux).

The mirror image of scripts/setup.py. It reverses what setup did, in roughly
reverse order, and never touches anything ClaudeBoost did not create.

Run it directly:
    python scripts/uninstall.py              # preview prompt, then remove CB footprint
    python scripts/uninstall.py --dry-run    # show the plan, change nothing
    python scripts/uninstall.py --yes        # skip the confirm prompt
    python scripts/uninstall.py --purge      # also remove pip pkg, indexes, PATH, shared MCPs

Default scope (no --purge) removes only ClaudeBoost's own footprint:
  - CB and clean-rag hooks, env vars, statusLine, and the permission entries
    setup added, out of ~/.claude/settings.json
  - the ~/.claude symlinks (CLAUDE.md, commands) and copied files
    (ensure-setup.py, claudeboost-home.txt)
  - the clean-rag user assets clean-rag/install.py drops in ~/.claude: the
    hook-run.py launcher, the research and triage agents, and the research skills
  - the rag-server MCP registration (legacy)
  - stops the running RAG HTTP daemon and clears its temp sentinel

--purge additionally:
  - pip uninstalls the rag-server package
  - removes the ClaudeBoost .rag-index directory
  - strips the netcoredbg PATH line from ~/.profile
  - deregisters the shared MCP servers (mcp-debugger, playwright)

What it never does: delete the repo, delete a real ~/.claude/CLAUDE.md you wrote,
remove slash commands you added yourself, or uninstall shared ML deps.

Re-running setup.py puts everything back, so the default path is fully reversible.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Colors, same scheme as setup.py so the two read as a pair.
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
def _plan(msg: str) -> None: _say(f"[DRY] would {msg}", "cyan")


# ---------------------------------------------------------------------------
# Paths, resolved exactly like setup.py so we target the same files.
# ---------------------------------------------------------------------------
BOOST_HOME = Path(__file__).resolve().parent.parent
BOOST_HOME_POSIX = BOOST_HOME.as_posix()
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
MCP_PATH = CLAUDE_DIR / "mcp.json"
CLAUDE_JSON_PATH = Path.home() / ".claude.json"

IS_WINDOWS = os.name == "nt"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# Set by main() from CLI flags.
DRY_RUN = False
PURGE = False


# ---------------------------------------------------------------------------
# JSON helpers, match setup.py (UTF-8, BOM-tolerant read, BOM-less write).
# ---------------------------------------------------------------------------
def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        raise

def write_json(path: Path, data: Any) -> None:
    if DRY_RUN:
        return
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Permission entries setup adds. Imported from setup.py when possible so the
# two stay in sync; falls back to a local copy if the import ever breaks.
# ---------------------------------------------------------------------------
def _setup_permission_sets() -> tuple[list[str], list[str], str]:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import setup  # noqa: F401, only constants are read, main() is not called
        return list(setup._GIT_WRITE_ASK), list(setup._GIT_DENY), setup._BASH_CATCHALL
    except Exception:
        # Conservative fallback: only the entries we are certain setup added.
        _warn("Could not import setup.py for permission lists, using a minimal fallback set.")
        return (
            ["Bash(git commit **)", "Bash(git push **)", "Bash(git add **)"],
            ["Bash(git push --force origin main **)", "Bash(git branch -D **)"],
            "Bash",
        )


# Hooks installed by setup all run through "$CLAUDEBOOST_PYTHON" / live under
# "$CLAUDEBOOST_HOME". Prompt-type hooks carry these sentinel phrases. Both lists
# below identify a hook as ClaudeBoost's so we remove only what setup added.
_CB_COMMAND_MARKERS = (
    "CLAUDEBOOST_HOME", "CLAUDEBOOST_PYTHON", "ensure-setup.py", "rag-statusline",
    # Legacy clean-rag marker, kept so older installs still get cleaned.
    "proof-gate.py",
    # Current clean-rag hooks. install.py wraps each one through hook-run.py, so
    # the launcher marker alone catches them all, but list the hook filenames too
    # in case an unwrapped registration is ever left behind.
    "hook-run.py", "research-gate.py", "research-record.py", "rag-enforce.py",
    "reindex-after-edit.py", "code-pattern-inject.py", "graph-context-inject.py",
)
_CB_PROMPT_SENTINELS = (
    "Quality-first routing",
    "CONSULT vs AUTO",
    "RAG HTTP API",
    "WORKSPACE CREATION CHECK",
    "PROCESS KILL SAFETY",
    "CONTEXT PRESERVATION",
    "CLEAN-RAG ENFORCEMENT",
)


def _is_cb_command(cmd: str) -> bool:
    return any(m in cmd for m in _CB_COMMAND_MARKERS)

def _is_cb_prompt(text: str) -> bool:
    return any(s in text for s in _CB_PROMPT_SENTINELS)


# ---------------------------------------------------------------------------
# Step 1, settings.json: hooks, statusLine, env, permissions.
# ---------------------------------------------------------------------------
def _remove_hooks(settings: dict) -> int:
    hooks = settings.get("hooks") or {}
    removed = 0
    for hook_type in list(hooks.keys()):
        new_entries = []
        for entry in hooks[hook_type] or []:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not inner:
                new_entries.append(entry)
                continue
            kept = []
            for h in inner:
                cmd = (h.get("command", "") or "") if isinstance(h, dict) else ""
                txt = (h.get("prompt", "") or "") if isinstance(h, dict) else ""
                if (cmd and _is_cb_command(cmd)) or (txt and _is_cb_prompt(txt)):
                    removed += 1
                else:
                    kept.append(h)
            if kept:
                entry["hooks"] = kept
                new_entries.append(entry)
            # else: every inner hook was ClaudeBoost's, drop the whole entry
        if new_entries:
            hooks[hook_type] = new_entries
        else:
            del hooks[hook_type]
    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)
    return removed


def revert_settings() -> None:
    _info("\n[1/5] Reverting ~/.claude/settings.json...")
    if not SETTINGS_PATH.exists():
        _skip("settings.json not found, nothing to revert")
        return
    try:
        settings = read_json(SETTINGS_PATH, {})
    except json.JSONDecodeError:
        _err("settings.json is malformed JSON, fix it by hand, then re-run uninstall.")
        return

    # Hooks
    removed = _remove_hooks(settings)
    if removed:
        (_plan if DRY_RUN else _ok)(f"remove {removed} ClaudeBoost hook(s)" if DRY_RUN
                                    else f"removed {removed} ClaudeBoost hook(s)")
    else:
        _skip("no ClaudeBoost hooks present")

    # statusLine
    sl = settings.get("statusLine")
    if isinstance(sl, dict) and _is_cb_command(sl.get("command", "")):
        settings.pop("statusLine", None)
        (_plan if DRY_RUN else _ok)("remove RAG statusLine" if DRY_RUN else "removed RAG statusLine")
    else:
        _skip("statusLine not ClaudeBoost's, leaving it")

    # env vars
    env = settings.get("env") or {}
    dropped = [k for k in ("CLAUDEBOOST_HOME", "CLAUDEBOOST_PYTHON", "CLAUDEBOOST_BASH_GUARD", "CLEAN_RAG_HOME") if k in env]
    for k in dropped:
        env.pop(k, None)
    if env:
        settings["env"] = env
    else:
        settings.pop("env", None)
    if dropped:
        (_plan if DRY_RUN else _ok)(f"remove env vars: {', '.join(dropped)}" if DRY_RUN
                                    else f"removed env vars: {', '.join(dropped)}")
    else:
        _skip("no ClaudeBoost env vars present")

    # permissions
    ask_set, deny_set, bash_catchall = _setup_permission_sets()
    perms = settings.get("permissions") or {}
    n_allow = n_ask = n_deny = 0
    if isinstance(perms.get("allow"), list) and bash_catchall in perms["allow"]:
        perms["allow"].remove(bash_catchall)
        n_allow = 1
    if isinstance(perms.get("ask"), list):
        before = len(perms["ask"])
        perms["ask"] = [e for e in perms["ask"] if e not in ask_set]
        n_ask = before - len(perms["ask"])
    if isinstance(perms.get("deny"), list):
        before = len(perms["deny"])
        perms["deny"] = [e for e in perms["deny"] if e not in deny_set]
        n_deny = before - len(perms["deny"])
    for key in ("allow", "ask", "deny"):
        if key in perms and not perms[key]:
            perms.pop(key)
    if perms:
        settings["permissions"] = perms
    else:
        settings.pop("permissions", None)
    if n_allow or n_ask or n_deny:
        msg = f"permission entries: -{n_allow} allow, -{n_ask} ask, -{n_deny} deny (incl. git safety prompts)"
        (_plan if DRY_RUN else _ok)((f"remove {msg}") if DRY_RUN else (f"removed {msg}"))
    else:
        _skip("no ClaudeBoost permission entries present")

    write_json(SETTINGS_PATH, settings)
    if not DRY_RUN:
        _ok("settings.json rewritten (user entries preserved)")


# ---------------------------------------------------------------------------
# Step 2, ~/.claude files: symlinks and copied helpers.
# ---------------------------------------------------------------------------
def _is_link_into_repo(path: Path) -> bool:
    """True if path is a symlink/junction that resolves inside the repo."""
    try:
        if not (path.is_symlink() or path.resolve(strict=False) != path):
            return False
        resolved = path.resolve(strict=False)
        return str(resolved).startswith(str(BOOST_HOME))
    except OSError:
        return False


def _unlink(path: Path) -> None:
    if DRY_RUN:
        return
    try:
        path.unlink()
    except (IsADirectoryError, PermissionError, OSError):
        # Windows junctions present as dirs, rmdir removes the link, not the target.
        os.rmdir(path)


def remove_claude_files() -> None:
    _info("\n[2/5] Removing ~/.claude symlinks and copied files...")

    # CLAUDE.md, only if it's a symlink into the repo. Never delete a real file.
    claude_md = CLAUDE_DIR / "CLAUDE.md"
    if claude_md.is_symlink() or (claude_md.exists() and _is_link_into_repo(claude_md)):
        if _is_link_into_repo(claude_md):
            _unlink(claude_md)
            (_plan if DRY_RUN else _ok)("remove CLAUDE.md symlink" if DRY_RUN else "removed CLAUDE.md symlink")
        else:
            _warn("~/.claude/CLAUDE.md is a symlink to something outside the repo, leaving it")
    elif claude_md.exists():
        _warn("~/.claude/CLAUDE.md is a real file (not a ClaudeBoost symlink), leaving it")
    else:
        _skip("~/.claude/CLAUDE.md not present")

    # commands/, symlink into repo (install.sh path) or a real dir mirror (setup.py path).
    commands = CLAUDE_DIR / "commands"
    if _is_link_into_repo(commands):
        _unlink(commands)
        (_plan if DRY_RUN else _ok)("remove commands symlink" if DRY_RUN else "removed commands symlink")
    elif commands.is_dir():
        repo_cmds = {p.name for p in (BOOST_HOME / ".claude" / "commands").glob("*.md")}
        removed = 0
        for md in commands.glob("*.md"):
            if md.name in repo_cmds:
                if not DRY_RUN:
                    md.unlink()
                removed += 1
        leftover = sum(1 for _ in commands.glob("*"))
        if DRY_RUN:
            _plan(f"remove {removed} mirrored slash command file(s) (keeping any you added)")
        else:
            _ok(f"removed {removed} mirrored slash command file(s) (kept your own)")
            # Drop the dir only if our removal emptied it.
            if leftover == 0:
                try:
                    commands.rmdir()
                    _ok("removed empty ~/.claude/commands dir")
                except OSError:
                    pass
    else:
        _skip("~/.claude/commands not present")

    # Copied helpers.
    for name in ("ensure-setup.py", "claudeboost-home.txt"):
        p = CLAUDE_DIR / name
        if p.exists():
            _unlink(p)
            (_plan if DRY_RUN else _ok)(f"remove {name}" if DRY_RUN else f"removed {name}")
        else:
            _skip(f"~/.claude/{name} not present")

    # clean-rag user assets, dropped into ~/.claude by clean-rag/install.py's
    # install_user_assets(): the hook launcher, the two research agents, and the
    # two research skills. clean-rag has no uninstaller of its own, so we clean
    # them here as part of the shared footprint.
    launcher = CLAUDE_DIR / "hook-run.py"
    if launcher.exists():
        _unlink(launcher)
        (_plan if DRY_RUN else _ok)("remove hook-run.py" if DRY_RUN else "removed hook-run.py")
    else:
        _skip("~/.claude/hook-run.py not present")

    for agent_name in ("research-agent.md", "triage-agent.md"):
        p = CLAUDE_DIR / "agents" / agent_name
        if p.exists():
            _unlink(p)
            (_plan if DRY_RUN else _ok)(f"remove agents/{agent_name}" if DRY_RUN
                                        else f"removed agents/{agent_name}")
        else:
            _skip(f"~/.claude/agents/{agent_name} not present")

    for skill_name in ("research", "research-routing"):
        d = CLAUDE_DIR / "skills" / skill_name
        if d.is_dir():
            if not DRY_RUN:
                shutil.rmtree(d, ignore_errors=True)
            (_plan if DRY_RUN else _ok)(f"remove skills/{skill_name}" if DRY_RUN
                                        else f"removed skills/{skill_name}")
        else:
            _skip(f"~/.claude/skills/{skill_name} not present")


# ---------------------------------------------------------------------------
# Step 3, MCP registrations.
# ---------------------------------------------------------------------------
def _run(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except FileNotFoundError as e:
        return 127, str(e)


def _claude_cmd() -> list[str] | None:
    for candidate in ("claude", "claude.cmd"):
        path = shutil.which(candidate)
        if path:
            return ["cmd", "/c", path] if candidate.endswith(".cmd") else [path]
    return None


def _strip_mcp_server(path: Path, name: str, label: str) -> None:
    if not path.exists():
        _skip(f"{label} not found")
        return
    try:
        data = read_json(path, {})
    except json.JSONDecodeError:
        _warn(f"{label} is malformed, leaving it alone")
        return
    if name in data.get("mcpServers", {}):
        if not DRY_RUN:
            del data["mcpServers"][name]
            write_json(path, data)
        (_plan if DRY_RUN else _ok)(f"remove {name} from {label}" if DRY_RUN
                                    else f"removed {name} from {label}")
    else:
        _skip(f"{name} not in {label}")


def _mcp_remove(claude: list[str] | None, name: str) -> None:
    if claude is None:
        _skip(f"claude CLI not found, remove {name} MCP by hand if needed")
        return
    if DRY_RUN:
        _plan(f"deregister {name} MCP (claude mcp remove {name})")
        return
    rc, _ = _run(claude + ["mcp", "remove", name, "--scope", "user"])
    if rc != 0:
        rc, _ = _run(claude + ["mcp", "remove", name])
    if rc == 0:
        _ok(f"deregistered {name} MCP")
    else:
        _skip(f"{name} MCP not registered (or already gone)")


def deregister_mcp() -> None:
    _info("\n[3/5] Deregistering MCP servers...")
    claude = _claude_cmd()

    # rag-server is ClaudeBoost's own, always remove (legacy stdio entry + CLI reg).
    _strip_mcp_server(MCP_PATH, "rag-server", "~/.claude/mcp.json")
    _strip_mcp_server(CLAUDE_JSON_PATH, "rag-server", "~/.claude.json")
    _mcp_remove(claude, "rag-server")

    # Shared tools, only on --purge, since other projects may use them.
    if PURGE:
        for name in ("mcp-debugger", "playwright"):
            _mcp_remove(claude, name)
    else:
        _skip("mcp-debugger / playwright left registered (use --purge to remove shared MCPs)")


# ---------------------------------------------------------------------------
# Step 4, stop the RAG daemon and clear its session sentinel.
# ---------------------------------------------------------------------------
def _rag_index_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    override = os.environ.get("RAG_INDEX_DIR")
    if override:
        return Path(override)
    if local_appdata:
        return Path(local_appdata) / "rag-server-index"
    return BOOST_HOME / "mcp-rag-server" / ".rag-index"


def stop_rag_server() -> None:
    _info("\n[4/5] Stopping the RAG HTTP server...")
    stop_script = BOOST_HOME / "scripts" / "restart-rag.py"
    if DRY_RUN:
        _plan(f"stop the RAG daemon ({stop_script.name} sends SIGTERM to rag_server)")
    elif stop_script.exists():
        rc, out = _run([sys.executable, str(stop_script)])
        last = out.splitlines()[0] if out else ""
        if rc == 0:
            _ok(f"RAG server stopped ({last or 'no process was running'})")
        else:
            _warn(f"could not stop RAG server cleanly: {last}")
    else:
        _warn("restart-rag.py missing, stop the server by hand if it's running")

    # Drop the cached server-info file so a future setup starts fresh.
    info_file = _rag_index_dir() / ".server.json"
    if info_file.exists():
        if not DRY_RUN:
            info_file.unlink()
        (_plan if DRY_RUN else _ok)("remove .server.json" if DRY_RUN else "removed .server.json")

    # Session sentinel that session-primer.py looks for.
    sentinel = Path(tempfile.gettempdir()) / "claudeboost_rag_ok"
    if sentinel.exists():
        if not DRY_RUN:
            sentinel.unlink()
        (_plan if DRY_RUN else _ok)("clear RAG session sentinel" if DRY_RUN else "cleared RAG session sentinel")
    else:
        _skip("RAG session sentinel not present")


# ---------------------------------------------------------------------------
# Step 5, --purge extras: pip package, index dir, ~/.profile PATH line.
# ---------------------------------------------------------------------------
def purge_extras() -> None:
    if not PURGE:
        return
    _info("\n[5/5] Purge: pip package, indexes, PATH edits...")

    # pip uninstall the rag-server package.
    if DRY_RUN:
        _plan("pip uninstall rag-server")
    else:
        rc, out = _run([sys.executable, "-m", "pip", "uninstall", "rag-server", "-y"])
        if rc == 0:
            _ok("rag-server package uninstalled")
        else:
            _skip("rag-server package not installed (or pip declined)")

    # Remove the ClaudeBoost RAG index directory (vector store + graph.db).
    index_dir = _rag_index_dir()
    if index_dir.exists():
        if DRY_RUN:
            _plan(f"remove RAG index dir {index_dir}")
        else:
            shutil.rmtree(index_dir, ignore_errors=True)
            _ok(f"removed RAG index dir {index_dir}")
    else:
        _skip("RAG index dir not present")
    _warn("per-project indexes under <project>/workspace/.rag-index/ are left alone, remove those by hand")

    # Strip the netcoredbg PATH line from ~/.profile (POSIX). Windows uses the
    # registry, which we don't rewrite automatically.
    if IS_WINDOWS:
        _warn("netcoredbg PATH was set in the user registry, remove ~/.netcoredbg from PATH by hand if you want it gone")
    else:
        profile = Path.home() / ".profile"
        if profile.exists():
            lines = profile.read_text(encoding="utf-8").splitlines(keepends=True)
            kept = [ln for ln in lines if ".netcoredbg" not in ln]
            if len(kept) != len(lines):
                if DRY_RUN:
                    _plan("strip the netcoredbg PATH line from ~/.profile")
                else:
                    profile.write_text("".join(kept), encoding="utf-8")
                    _ok("stripped netcoredbg PATH line from ~/.profile")
            else:
                _skip("no netcoredbg PATH line in ~/.profile")
        else:
            _skip("~/.profile not present")

    _warn("shared ML deps (sentence-transformers, edge-tts, etc.) are left installed, uninstall by hand if you want them gone")


# ---------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------
def _confirm() -> bool:
    scope = "FULL PURGE" if PURGE else "ClaudeBoost footprint"
    _warn(f"\nAbout to uninstall ClaudeBoost ({scope}). This edits ~/.claude/settings.json,")
    _warn("removes the ~/.claude symlinks/helpers, deregisters rag-server, and stops the RAG server.")
    if PURGE:
        _warn("PURGE also pip-uninstalls rag-server, deletes the RAG index, removes the PATH edit,")
        _warn("and deregisters mcp-debugger + playwright.")
    _warn("Re-running scripts/setup.py puts the default footprint back.")
    try:
        ans = input("\nProceed? [y/N] ").strip().lower()
    except EOFError:
        _err("No interactive input available. Re-run with --yes to confirm, or --dry-run to preview.")
        return False
    return ans in ("y", "yes")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    global DRY_RUN, PURGE
    parser = argparse.ArgumentParser(description="Uninstall ClaudeBoost (reverse of setup.py).")
    parser.add_argument("--purge", action="store_true",
                        help="also remove pip package, RAG index, PATH edit, and shared MCPs")
    parser.add_argument("--dry-run", action="store_true",
                        help="show the plan, change nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    args = parser.parse_args()
    DRY_RUN = args.dry_run
    PURGE = args.purge

    _info("\n=== ClaudeBoost Uninstall ===")
    print(f"ClaudeBoost home: {BOOST_HOME}")
    print(f"Claude config dir: {CLAUDE_DIR}")
    print(f"Platform: {platform.system()} ({sys.platform})")
    print(f"Mode: {'DRY RUN (no changes)' if DRY_RUN else ('FULL PURGE' if PURGE else 'footprint only')}")

    if not DRY_RUN and not args.yes:
        if not _confirm():
            _info("\nAborted. Nothing was changed.")
            return 1

    revert_settings()
    remove_claude_files()
    deregister_mcp()
    stop_rag_server()
    purge_extras()

    if DRY_RUN:
        _info("\n=== Dry run complete, nothing was changed ===")
        print("Run again without --dry-run to apply, or add --purge for the full removal.")
    else:
        _info("\n=== ClaudeBoost Uninstalled ===")
        print("  - ~/.claude/settings.json reverted (your own entries preserved)")
        print("  - symlinks and copied helpers removed")
        print("  - rag-server deregistered, RAG server stopped")
        if PURGE:
            print("  - pip package, RAG index, and PATH edit removed")
        _say("\nThe repo itself was left in place, delete the ClaudeBoost folder if you want it gone.", "yellow")
        _say("Restart any open Claude Code sessions so they drop the removed hooks and commands.", "yellow")
        print("\nChanged your mind? Run scripts/setup.py to reinstall.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
