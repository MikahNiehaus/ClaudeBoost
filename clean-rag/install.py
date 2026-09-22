#!/usr/bin/env python3
"""clean-rag installer. Registers hooks and sets up the environment.

Usage:
  python clean-rag/install.py                # full install
  python clean-rag/install.py --skip-deps    # skip pip install
"""
# Required, not stylistic. This file annotates with PEP 604 unions
# (`list[str] | None` at _claude_cmd, `str | None` at _wrap_command,
# `Path | None` at _hook_target_script). Those are evaluated at runtime on
# Python 3.9 and raise TypeError at import, which takes the installer down
# before it can print its own version message. setup.py documents a 3.9 floor.
from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

CLEAN_RAG_HOME = Path(__file__).resolve().parent
CLAUDE_DIR = Path.home() / ".claude"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"

# Hook sentinels: unique strings in hook commands for idempotent registration
RAG_ENFORCE_SENTINEL = "rag-enforce.py"
REINDEX_SENTINEL = "reindex-after-edit.py"
VERIFY_AFTER_EDIT_SENTINEL = "verify-after-edit.py"
SESSION_SENTINEL = "CLEAN-RAG ENFORCEMENT"
GRAPH_CONTEXT_SENTINEL = "graph-context-inject.py"
SPEC_COMPLIANCE_GATE_SENTINEL = "spec-compliance-gate.py"
CODE_PATTERN_INJECT_SENTINEL = "code-pattern-inject.py"
RESEARCH_GATE_SENTINEL = "research-gate.py"
RESEARCH_GATE_BASH_SENTINEL = "research-gate-bash.py"
RESEARCH_RECORD_SENTINEL = "research-record.py"
AUTO_TEST_GATE_SENTINEL = "auto-test-gate.py"
VERIFIER_GATE_SENTINEL = "verifier-gate.py"
VERIFIER_RECORD_SENTINEL = "verifier-record.py"
RECORD_EDIT_SENTINEL = "record-edit.py"
LINT_GATE_SENTINEL = "lint-gate.py"


def _say(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


def _differing_lines(src: Path, dst: Path) -> int:
    """How many lines differ between two text files. -1 when either is unreadable.

    Read as text so a pure CRLF/LF difference counts as zero: a git checkout can
    flip line endings without anyone having edited anything.
    """
    try:
        a = src.read_text(encoding="utf-8", errors="replace").splitlines()
        b = dst.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return -1
    return sum(
        1 for line in difflib.unified_diff(a, b, n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    )


def read_json(path: Path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 1: Create directories
# ---------------------------------------------------------------------------
def ensure_directories() -> None:
    dirs = ["knowledge", "databases", "databases/_projects", "state",
            "server", "hooks", "cli"]
    for d in dirs:
        (CLEAN_RAG_HOME / d).mkdir(parents=True, exist_ok=True)
    _ok("Directories created")


def ensure_env_file() -> None:
    """Seed clean-rag/.env from the template on first install.

    The .env is gitignored, so a fresh checkout has none. Copy the committed
    .env.example over, but never clobber an existing .env, that's the machine's
    own config. config.py reads it (and a ClaudeBoost/.env one level up) at
    startup.
    """
    env = CLEAN_RAG_HOME / ".env"
    example = CLEAN_RAG_HOME / ".env.example"
    if env.exists():
        _ok(".env already present, left as is")
        return
    if not example.is_file():
        _warn(".env.example missing, skipping .env seed")
        return
    shutil.copy2(example, env)
    _ok("created clean-rag/.env from template")


# ---------------------------------------------------------------------------
# Copy the pieces that have to live under ~/.claude, not in the repo.
#
# The research agents, the two skills, and the hook launcher can't stay only in
# the repo: Claude Code reads agents from ~/.claude/agents, skills from
# ~/.claude/skills, and the launcher is referenced from ~/.claude/settings.json.
# So the repo holds the canonical copies under clean-rag/portable/, and this
# copies them into place. A clone plus one install run reproduces the whole
# setup on a new machine, which it could not before: the hooks were wired to run
# a launcher that nothing created and to satisfy a gate with agents that didn't
# exist.
# ---------------------------------------------------------------------------
def _alias_description(path: Path) -> str | None:
    """How writing `path` would also rewrite some other file, or None.

    Three mechanisms alias a destination, and each needs its own test:
    a hard link (several names, one inode), a symlink, and on Windows a
    junction. shutil.copyfile opens the destination "wb", which follows a
    symlink or junction and truncates an inode in place, so every one of them
    turns "write this file" into "rewrite a different file".

    Only the final path component is examined, deliberately. os.path.realpath
    would also flag an ordinary file whose PARENT is aliased: measured here, a
    plain file inside a junction has realpath != abspath while the file itself
    is perfectly ordinary. Refusing on that would break every install for
    anyone who keeps ~/.claude behind a junction or a dotfiles symlink, which
    is a normal setup. Aliasing of the parent is the user's own arrangement and
    writing files into it is exactly what this installer is for.

    The link count is read with follow_symlinks=False. The symlink test above
    already returns first, so today that flag changes no outcome; it is there
    so the count still describes the destination itself if these checks are
    ever reordered. Path.stat() would report a symlink target's count, which is
    1 for an ordinary file however many symlinks point at it.

    Returns None when the answer cannot be trusted, which keeps the caller on
    its previous behaviour rather than refusing an install over a stat quirk.
    A filesystem with no hard links (FAT32, exFAT) reports 1, and one that
    reports nothing useful degrades to the old behaviour. Note this covers the
    hard link case only: a filesystem can lack hard links and still carry
    symlinks or reparse points, which is why those are tested separately.
    """
    try:
        if path.is_symlink():
            try:
                return f"a symlink to {os.readlink(path)}"
            except OSError:
                return "a symlink"
        # os.path.isjunction is 3.12+. A junction is not a symlink as far as
        # is_symlink() is concerned (measured: it returns False), so without
        # this a junction would go undetected.
        if getattr(os.path, "isjunction", None) and os.path.isjunction(path):
            return "a junction"
        nlink = os.stat(path, follow_symlinks=False).st_nlink
    except OSError:
        return None
    if nlink and nlink > 1:
        return f"hard linked to {nlink - 1} other file(s)"
    return None


def _copy_file(src: Path, dst: Path) -> None:
    if not src.is_file():
        _warn(f"missing bundled file: {src.name}")
        return
    if dst.exists():
        # Aliasing is checked before mtime because it is the more specific
        # fact and it changes what the right advice is. An aliased destination
        # that is also newer used to report only the mtime story, which tells
        # the reader to "reconcile by hand" a file that is really someone
        # else's, so the accurate diagnosis never reached them.
        #
        # shutil.copyfile opens dst "wb", truncating the inode in place, so
        # every other name for it sees the new bytes. install.bat hard links
        # ~/.claude/CLAUDE.md to the repo's own tracked CLAUDE.md, and copying
        # over it rewrites a tracked file, leaving an unexplained `git diff` a
        # maintainer could commit.
        #
        # shutil.SameFileError does not cover this. It fires on
        # _samefile(src, dst), and here src is the portable copy while the link
        # is between dst and a third path, so src and dst really are different
        # files.
        alias = _alias_description(dst)
        if alias:
            # Identical content means the copy would change nothing, so there
            # is no hazard to report and nothing worth saying.
            if _differing_lines(src, dst) == 0:
                return
            _warn(
                f"{dst.name} in ~/.claude is {alias}. Writing it would rewrite "
                f"that file too, so the installer left it alone."
            )
            # No `del` instruction here, on purpose. Deleting the link and
            # re-running silently swaps the linked document for this bundled
            # copy and drops the link, and the run ends on a plain "installed"
            # line that gives the reader no sign their global instructions
            # just changed identity.
            _say(
                f"That link is how install.bat sets things up, and the file it "
                f"points at is already in use, so there is usually nothing to do."
            )
            _say(
                f"To use this bundled copy instead, replace the link yourself; "
                f"it then stops following the repo on git pull. Compare first:"
            )
            _say(f"diff \"{src}\" \"{dst}\"")
            return
        # Don't stomp a copy the user edited to be newer than the repo's: skip
        # it so a local tweak survives a re-run. That direction is deliberate
        # and stays — the installer preserves the local file and never resolves
        # a conflict on the user's behalf.
        #
        # What mtime cannot say is whether the two actually differ, and it is a
        # weak freshness signal generally (apenwarr, "mtime comparison
        # considered harmful"; moby/moby#9391 reached the same conclusion for
        # ADD cache invalidation). Left at mtime alone the skip reads as a
        # no-op, which is how ~/.claude/CLAUDE.md drifted hundreds of lines from
        # the repo copy while every install printed one bland line about it. So
        # compare content as well: stay quiet when the skip changes nothing, and
        # when it does, say how far apart they are and how to look.
        if dst.stat().st_mtime > src.stat().st_mtime:
            drift = _differing_lines(src, dst)
            if drift == 0:
                return
            extent = f"{drift} lines differ" if drift > 0 else "content unreadable"
            _warn(
                f"{dst.name} in ~/.claude is newer than the repo copy and {extent}, "
                f"leaving it. Nothing here will overwrite it; reconcile by hand:"
            )
            _say(f"diff \"{src}\" \"{dst}\"")
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    _ok(f"installed {dst.relative_to(CLAUDE_DIR.parent)}")


def install_user_assets() -> None:
    portable = CLEAN_RAG_HOME / "portable"
    if not portable.is_dir():
        _warn("clean-rag/portable not found, skipping user asset install")
        return

    CLAUDE_DIR.mkdir(parents=True, exist_ok=True)

    # The global instructions describing the research gate and the agents. Both
    # this installer and ClaudeBoost's setup.py (which delegates here) keep it
    # current. A newer local edit is preserved by _copy_file, so hand tweaks
    # survive a re-install.
    _copy_file(portable / "CLAUDE.md", CLAUDE_DIR / "CLAUDE.md")

    # The branch safety launcher. Lives outside the repo on purpose, so a branch
    # switch can't remove it out from under a live hook registration.
    _copy_file(portable / "hook-run.py", CLAUDE_DIR / "hook-run.py")

    # Agents. researcher and swiper are the two the research gate counts
    # (RESEARCH_AGENTS in hooks/research_state.py). bad-cop reviews afterward and
    # good-cop fixes what it finds. research-agent and verifier-agent used to be
    # named here and neither ships any more.
    for md in (portable / "agents").glob("*.md"):
        _copy_file(md, CLAUDE_DIR / "agents" / md.name)

    # Skills. Copied whole, so a skill can carry a scripts/ subfolder (the
    # powerpoint skill does). __pycache__ is excluded: running the skill's
    # helper leaves bytecode in the repo copy that has no business shipping.
    skills_src = portable / "skills"
    if skills_src.is_dir():
        shutil.copytree(skills_src, CLAUDE_DIR / "skills", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
        names = sorted(d.name for d in skills_src.iterdir() if d.is_dir())
        _ok(f"installed .claude/skills ({len(names)}: {', '.join(names)})")


# ---------------------------------------------------------------------------
# Step 2: Install Python deps
# ---------------------------------------------------------------------------
def install_deps() -> None:
    req_file = CLEAN_RAG_HOME / "requirements.txt"
    if not req_file.exists():
        _warn("requirements.txt not found, skipping pip install")
        return
    _say("Installing Python dependencies...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        _ok("Dependencies installed")
    else:
        _warn(f"pip install returned {result.returncode}: {result.stderr[:200]}")


# ---------------------------------------------------------------------------
# Step 2b: Install npm QA tools (best effort)
# ---------------------------------------------------------------------------
def install_npm_qa_tools() -> None:
    """Install npm QA tools for bad-cop and good-cop agents.

    Best effort: warns and continues if npm is not available or if any
    install fails. odiff provides pixel level screenshot diffing; jscpd
    provides duplication detection with an AI optimized reporter.
    """
    npm = shutil.which("npm")
    if not npm:
        _warn("npm not found, skipping QA tool install (odiff, jscpd)")
        _say("Install Node.js to enable visual diffing and duplication detection")
        return

    tools = [("odiff-bin", "odiff"), ("jscpd@5", "jscpd")]
    for package, binary in tools:
        if shutil.which(binary):
            _ok(f"{binary} already installed")
            continue
        _say(f"Installing {package}...")
        try:
            result = subprocess.run(
                [npm, "install", "-g", package],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                _ok(f"{package} installed")
            else:
                _warn(f"{package} install failed: {result.stderr[:200]}")
        except Exception as e:  # noqa: BLE001
            _warn(f"{package} install failed: {e}")


# ---------------------------------------------------------------------------
# Step 2b2: Register the debugging MCP servers (best effort)
#
# bad-cop and good-cop enumerate these servers' tools by literal name in their
# frontmatter, because Claude Code rejects mcp__<server>__* wildcards. An agent
# whose server was never registered silently has no such tool, so shipping the
# agents without registering the servers is a broken install, not a partial one.
#
# Mirrors ClaudeBoost's scripts/setup.py MCP_SERVERS table. Kept as its own copy
# so clean-rag stays installable standalone, without ClaudeBoost present.
# ---------------------------------------------------------------------------
#
# Dicts rather than (name, args) tuples since the credentialed and remote rows
# arrived: a tuple cannot carry a transport, a URL, a header or a required env
# var, so those rows would have silently degraded to a bare stdio registration
# here while working correctly in ClaudeBoost's copy. The shared keys are what
# tests/test_mcp_server_registration.py compares; label, hint and why are
# presentation only and live in scripts/setup.py alone.
MCP_SERVERS: list[dict] = [
    {"name": "mcp-debugger",
     "args": ["npx", "-y", "@debugmcp/mcp-debugger", "stdio"], "needs": "npx"},
    {"name": "playwright",
     "args": ["npx", "-y", "@playwright/mcp@latest"], "needs": "npx"},
    {"name": "test-coverage",
     "args": ["npx", "-y", "test-coverage-mcp"], "needs": "npx"},
    {"name": "chrome-devtools",
     "args": ["npx", "-y", "chrome-devtools-mcp@latest"], "needs": "npx"},
    {"name": "serena",
     "args": ["uvx", "--from", "git+https://github.com/oraios/serena",
              "serena", "start-mcp-server"], "needs": "uvx"},
    {"name": "ast-grep", "args": ["uvx", "ast-grep-mcp"], "needs": "uvx"},
    {"name": "context7",
     "args": ["npx", "-y", "@upstash/context7-mcp"], "needs": "npx"},
    {"name": "semgrep", "args": ["uvx", "semgrep-mcp"], "needs": "uvx"},
    {"name": "osv", "args": ["osv-scanner", "mcp"], "needs": "osv-scanner"},
    {"name": "arxiv", "args": ["uvx", "arxiv-mcp-server"], "needs": "uvx"},
    {"name": "socket", "args": [],
     "transport": "http", "url": "https://mcp.socket.dev/"},
    {"name": "antv-chart",
     "args": ["npx", "-y", "@antv/mcp-server-chart"], "needs": "npx"},
    {"name": "jupyter", "args": ["uvx", "jupyter-mcp-server@latest"],
     "needs": "uvx", "needs_env": "JUPYTER_TOKEN"},
    {"name": "github", "args": [],
     "transport": "http", "url": "https://api.githubcopilot.com/mcp/",
     "headers": {"Authorization": "Bearer ${GITHUB_MCP_TOKEN}"},
     "needs_env": "GITHUB_MCP_TOKEN"},
    {"name": "atlassian", "args": [],
     "transport": "http", "url": "https://mcp.atlassian.com/v1/mcp"},
]


def _claude_cmd() -> list[str] | None:
    """A subprocess safe `claude` invocation, or None if it is not on PATH.

    On Windows claude installs as claude.cmd, which subprocess cannot launch
    without going through cmd.exe.
    """
    for candidate in ("claude", "claude.cmd"):
        path = shutil.which(candidate)
        if path:
            return ["cmd", "/c", path] if candidate.endswith(".cmd") else [path]
    return None


def parse_mcp_list(stdout: str) -> dict[str, str]:
    """Map each server name in `claude mcp list` output to its OWN status text.

    Its own copy, for the same standalone reason as MCP_SERVERS above; the
    ClaudeBoost twin is scripts/setup.py's parse_mcp_list. Real output is a
    header line then one server per line, `<name>: <command-or-url> - <status>`:

        mcp-debugger: npx -y @debugmcp/mcp-debugger stdio - ✔ Connected
        claude.ai GitHub: https://api.githubcopilot.com/mcp - ! Needs authentication

    Names can contain spaces and commands can contain colons, so the name is
    everything before the FIRST ": " and the status everything after the LAST
    " - ". A bare `name in stdout` substring test instead matches a name that
    only appears inside another server's name or command, and silently skips
    registering the real one.
    """
    servers: dict[str, str] = {}
    for line in stdout.splitlines():
        name, sep, rest = line.partition(": ")
        if not sep or not name.strip():
            continue
        _, dash, status = rest.rpartition(" - ")
        servers[name.strip()] = status.strip() if dash else ""
    return servers


def _mcp_add_cmd(claude: list[str], server: dict) -> list[str]:
    """The registration command for one server row.

    The ClaudeBoost twin is scripts/setup.py's _server_json plus the branch in
    _register_one; kept as its own copy for the same standalone reason as
    MCP_SERVERS above.

    A remote or credentialed row goes through `add-json` rather than
    `claude mcp add --env K=V`, because --env is variadic and greedily consumes
    the server name when the two are adjacent (anthropics/claude-code#29221).
    JSON has no positional ambiguity.

    A credential is written as the literal `${VAR}` placeholder that Claude Code
    expands from the environment at launch, so the secret never lands in
    ~/.claude.json. Expansion fails soft on an unset var, which is why the
    caller checks needs_env first rather than trusting it.
    """
    name = server["name"]
    if server.get("transport") == "http":
        payload: dict = {"type": "http", "url": server["url"]}
        if server.get("headers"):
            payload["headers"] = server["headers"]
    elif server.get("env"):
        args = server["args"]
        payload = {"type": "stdio", "command": args[0], "args": args[1:],
                   "env": server["env"]}
    else:
        return claude + ["mcp", "add", name, "--scope", "user", "--"] + server["args"]
    return claude + ["mcp", "add-json", name, "--scope", "user", json.dumps(payload)]


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


# Byte-identical twin of scripts/setup.py's registration_action, kept here for
# the same standalone reason as MCP_SERVERS above. The two installers used to
# make this decision in separately hand-written control flow and had already
# drifted: setup.py checked prerequisites first, this file checked "already
# registered" first, so one machine got two different answers for one server.
# ClaudeBoost's tests/test_mcp_server_registration.py drives both copies over a
# scenario matrix, so a future divergence fails a test rather than shipping.
#
# Order is the contract. A missing prerequisite or credential is reported even
# when the server is already registered, because Claude Code expands ${VAR}
# from its own environment at launch: a registered row whose credential is
# unset still sends the literal "${VAR}" and fails at runtime. Answering
# "already registered" would hide exactly that.
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


def register_mcp_servers() -> None:
    """Register every debugging MCP server at user scope. Never fatal.

    Idempotent: reads `claude mcp list` once and skips anything already there.
    """
    _say("\nRegistering debugging MCP servers...")

    claude = _claude_cmd()
    if claude is None:
        _warn("claude CLI not found, skipping MCP server registration")
        return

    try:
        listed = subprocess.run(
            claude + ["mcp", "list"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        _warn(f"claude mcp list failed ({e}), skipping MCP server registration")
        return

    if listed.returncode != 0:
        _warn("claude mcp list failed, skipping MCP server registration")
        return

    registered = parse_mcp_list(listed.stdout)
    for server in MCP_SERVERS:
        name = server["name"]
        # Prerequisites are checked per server, not behind one global npx gate.
        # That gate used to skip the whole table when Node was absent, which
        # was right when every row was an npx package and wrong the moment uvx
        # and the remote HTTP rows arrived: none of those need Node.
        action, detail = registration_action(
            server, registered.get(name), resolve_tool, os.environ)

        if action == "skip-missing-tool":
            _warn(f"{name} needs {detail}, not found, skipping")
            continue
        if action == "skip-missing-credential":
            _warn(f"{name} needs {detail} in the environment, skipping")
            continue
        if action == "already-registered":
            _ok(f"{name} already registered")
            continue

        cmd = _mcp_add_cmd(claude, server)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
            )
        except Exception as e:  # noqa: BLE001
            _warn(f"{name} registration failed: {e}")
            continue
        if result.returncode == 0:
            # "registered", never "working". `claude mcp add` writes config and
            # does not start the server, so a zero exit is consistent with an
            # npx or uvx row that later exceeds the 30s connect timeout while
            # downloading its package.
            _ok(f"{name} registered — run /mcp to confirm it connects")
        else:
            _warn(f"{name} registration failed: {result.stderr[:200]}")
            _say(f"  Manually: {' '.join(cmd[1:])}")


# ---------------------------------------------------------------------------
# Step 2c: Install deck tooling for the powerpoint skill (best effort)
# ---------------------------------------------------------------------------
def _module_available(module: str) -> bool:
    """Is an importable module already present for this interpreter?

    The in-process counterpart of install_npm_qa_tools()'s shutil.which: it
    answers without spawning anything, so it cannot hang the installer the way
    `python -c "import x"` can when a package blocks at import time. find_spec
    locates the module without executing it, which is also why it is what the
    powerpoint skill's own helper uses (pptx_env._have_module).
    """
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:  # noqa: BLE001  a broken spec means "not usable", not a crash
        return False


# ---------------------------------------------------------------------------
# Claude Code plugins. Mirrors ClaudeBoost's scripts/setup.py PLUGINS table,
# kept as its own copy for the same standalone reason as MCP_SERVERS above.
# `marketplace` is what `claude plugin marketplace add` takes, `name` is the
# plugin@marketplace id `claude plugin install` takes. Both steps are needed;
# adding the marketplace alone installs nothing.
# ---------------------------------------------------------------------------
PLUGINS: list[dict] = [
    {
        "name": "ponytail@ponytail",
        "marketplace": "DietrichGebert/ponytail",
        "needs_node": True,
    },
    # PreToolUse, so an over-long comment is refused rather than written and
    # then nudged. Python, no node needed.
    {
        "name": "pipe-down@claude-pipe-down",
        "marketplace": "hoo29/claude-pipe-down",
    },
]


def install_plugins() -> None:
    """Install every plugin in PLUGINS.

    Idempotent: `claude plugin list` is read once and anything already there is
    skipped. Best effort, same contract as register_mcp_servers. A plugin's
    hooks run as the user on every prompt, so each row is a trust decision.
    """
    if not PLUGINS:
        return

    claude = _claude_cmd()
    if claude is None:
        _warn("claude CLI not found, skipping plugin install")
        return

    try:
        # encoding and errors are load bearing: `claude plugin list` prints a
        # check mark, and under cp1252 a bare text=True decodes to None, which
        # silently reinstalls every row on every run.
        listed = subprocess.run(
            claude + ["plugin", "list"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        _warn(f"claude plugin list failed ({e}), skipping plugin install")
        return

    if listed.returncode != 0:
        _warn("claude plugin list failed, skipping plugin install")
        return

    installed = listed.stdout or ""

    for plugin in PLUGINS:
        name = plugin["name"]
        if name in installed:
            _ok(f"{name} already installed")
            continue

        # Its lifecycle hooks are Node. Without node they fail on every prompt.
        if plugin.get("needs_node") and resolve_tool("node") is None:
            _warn(f"{name} needs node on PATH, skipping")
            continue

        try:
            added = subprocess.run(
                claude + ["plugin", "marketplace", "add", plugin["marketplace"]],
                capture_output=True, text=True, timeout=120,
            )
            if added.returncode != 0:
                _warn(f"could not add marketplace {plugin['marketplace']}, skipping {name}")
                continue

            done = subprocess.run(
                claude + ["plugin", "install", name],
                capture_output=True, text=True, timeout=180,
            )
        except Exception as e:  # noqa: BLE001
            _warn(f"{name} install failed ({e})")
            continue

        if done.returncode == 0:
            _ok(f"{name} installed")
        else:
            _warn(f"{name} install failed, run: claude plugin install {name}")


def install_pptx_tools() -> None:
    """Install what the powerpoint skill needs to build and narrate a deck.

    Best effort, same contract as install_npm_qa_tools: warn and continue,
    never abort. python-pptx builds the deck and edge-tts voices the optional
    narration, both pip installable. LibreOffice, poppler and ffmpeg are
    native packages, so they are only detected here and reported with a
    manual install hint; auto-installing them across three OS package
    managers is a worse failure mode than a warning.
    """
    packages = [("python-pptx", "pptx"), ("edge-tts", "edge_tts")]
    for package, module in packages:
        if _module_available(module):
            _ok(f"{package} already installed")
            continue
        _say(f"Installing {package}...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", package],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode == 0:
                _ok(f"{package} installed")
            else:
                _warn(f"{package} install failed: {result.stderr[:200]}")
        except Exception as e:  # noqa: BLE001
            _warn(f"{package} install failed: {e}")

    # Native tools. The skill's own helper knows the per-OS search paths, so
    # ask it rather than duplicating that list here.
    helper = CLEAN_RAG_HOME / "portable" / "skills" / "powerpoint" / "scripts" / "pptx_env.py"
    natives = [
        ("soffice", "LibreOffice", "render and video",
         "winget install TheDocumentFoundation.LibreOffice | brew install --cask libreoffice | apt install libreoffice"),
        ("pdftoppm", "poppler", "slide images",
         "winget install oschwartz10612.Poppler | brew install poppler | apt install poppler-utils"),
        ("ffmpeg", "ffmpeg", "narrated video",
         "winget install Gyan.FFmpeg | brew install ffmpeg | apt install ffmpeg"),
    ]
    if not helper.is_file():
        _warn("powerpoint skill helper not found, skipping native tool detection")
        return
    for probe, label, purpose, how in natives:
        try:
            result = subprocess.run(
                [sys.executable, str(helper), probe],
                capture_output=True, text=True, timeout=60,
            )
        except Exception as e:  # noqa: BLE001
            _warn(f"could not probe for {label}: {e}")
            continue
        if result.returncode == 0:
            _ok(f"{label} found at {result.stdout.strip()}")
        else:
            _warn(f"{label} not found, powerpoint skill loses {purpose}")
            _say(f"  {how}")


# ---------------------------------------------------------------------------
# Hook registration helpers
# ---------------------------------------------------------------------------

# Lives in ~/.claude/, deliberately outside the repo, because that's the whole
# point of it.
HOOK_RUNNER = Path.home() / ".claude" / "hook-run.py"

# Portable launcher for clean-rag's own hooks: an env var each install resolves
# per machine, living in the repo so it can't drift from the hooks it wraps.
# Foreign hooks keep the shared ~/.claude/hook-run.py.
PORTABLE_HOOK_RUNNER = "$CLEAN_RAG_HOME/portable/hook-run.py"

# A hook is clean-rag's to wipe and rebuild if its command or prompt carries one
# of these. Every clean-rag command references $CLEAN_RAG_HOME; the lone prompt
# hook carries the session sentinel. ClaudeBoost ($CLAUDEBOOST_HOME) and user
# hooks match neither, so they're left alone.
CLEAN_RAG_OWNED_MARKERS = ("$CLEAN_RAG_HOME", SESSION_SENTINEL)


# The runner spliced in front of a compound `if`. That is what the old
# single-interpreter regex produced when handed `_py_cmd()`'s chain: it captured
# the keyword `if` as the interpreter. Matched here so the corruption can be
# repaired rather than read as "already wrapped".
_MANGLED_IF = re.compile(
    r'^(\s*if\s+)("[^"]*hook-run\.py"|\S*hook-run\.py)\s+(?=command\s)'
)

# The interpreter of one branch in that chain. Only a branch body follows `then`
# or `else`, so this cannot match the `command -v` test itself, which is the
# mistake the old regex made.
_BRANCH_INTERPRETER = re.compile(r'\b(then|else)\s+("[^"]*"|[^\s;]+)(\s+)')


def _is_compound(command: str) -> bool:
    """True for a shell if/elif/else chain rather than `<interpreter> <script>`."""
    return command.lstrip().startswith("if ")


def _unmangle_command(command: str) -> str:
    """Strip a runner that was spliced in front of a compound `if`."""
    return _MANGLED_IF.sub(r"\1", command, count=1)


def _wrap_compound(command: str, runner: str) -> str:
    """Insert the runner into each branch of an if/elif/else chain.

    Per branch, not once at the front: each branch runs its own interpreter, so
    each needs its own wrap. Branches already carrying the runner are left as
    they are, which is what makes a second install a no-op instead of a double
    wrap.
    """
    def wrap_branch(match: re.Match) -> str:
        keyword, interpreter, gap = match.group(1), match.group(2), match.group(3)
        body = command[match.end():].split(";", 1)[0]
        if "hook-run.py" in body:
            return match.group(0)
        return f'{keyword} {interpreter} "{runner}"{gap}'

    return _BRANCH_INTERPRETER.sub(wrap_branch, command)


def _wrap_command(command: str, runner: str | None = None) -> str:
    """Route a hook command through hook-run.py so a branch switch can't brick Claude.

    Hook commands are registered in the global settings.json, which does not
    change when you check out a different branch. The scripts they point at do
    live in the repo. So a branch that predates a hook leaves a live registration
    aimed at nothing, python exits 2, and Claude Code reads exit 2 from a
    PreToolUse hook as "block this tool call". Not a warning. Every Edit, Write,
    and Bash refused until you switch back.

    Measured on this repo's real branches: switching to main breaks 4 live hooks,
    2 of them blocking. The two feature branches break 11, with 4 blocking.

    hook-run.py runs the script if it's there, exits 0 if it isn't, and passes
    real exit codes straight through so a genuine gate can still block a genuine
    edit. It only swallows absence.

    Two command shapes arrive here. A simple `<interpreter> <script>`, which is
    what clean-rag's own registrations emit, and the if/elif/else fallback chain
    ClaudeBoost's `_py_cmd()` emits. The chain needs the runner inside each
    branch, because the thing at the front of it is the keyword `if`, not an
    interpreter. Wrapping the front of a chain produced
    `if "<runner>" command -v ...`, which corrupted 29 live registrations: the
    runner ran against the argument `command`, found no such script, exited 0,
    so the test passed and the real script ran unwrapped. The protection was
    silently absent while every hook still appeared to work.
    """
    if not command or ".py" not in command:
        return command

    if runner is None:
        runner = str(HOOK_RUNNER).replace("\\", "/")

    # Repair that corruption before deciding anything else. A mangled command
    # contains "hook-run.py" but is NOT wrapped, so the bare substring cannot
    # be trusted as an "already done" signal the way it once was.
    command = _unmangle_command(command)

    if _is_compound(command):
        return _wrap_compound(command, runner)

    if "hook-run.py" in command:
        return command

    # Split the interpreter off the front, keep whatever it was.
    match = re.match(r'^\s*("[^"]*"|\S+)\s+(.*)$', command)
    if not match:
        return command

    interpreter, rest = match.group(1), match.group(2).strip()
    return f'{interpreter} "{runner}" {rest}'


def _hook_target_script(command: str) -> Path | None:
    """The .py a hook command actually runs (ignoring the hook-run.py wrapper)."""
    scripts = [m for m in re.findall(r'"([^"]*\.py)"', command)
               if "hook-run.py" not in m]
    if not scripts:
        scripts = [m for m in re.findall(r'(\S+\.py)', command)
                   if "hook-run.py" not in m]
    if not scripts:
        return None
    raw = scripts[-1]
    expanded = os.path.expandvars(os.path.expanduser(raw))
    return Path(expanded.replace("\\", "/"))


def wipe_clean_rag_hooks() -> None:
    """Remove every hook clean-rag owns, so the registrations that follow rebuild
    the whole set from a clean slate.

    Ownership is by marker (CLEAN_RAG_OWNED_MARKERS): clean-rag's command hooks all
    carry $CLEAN_RAG_HOME and its one prompt hook carries the session sentinel.
    ClaudeBoost ($CLAUDEBOOST_HOME) and user hooks match neither, so they survive.
    This makes a re-install deterministic: no stale entry lingers, and no duplicate
    forms appear when a command path or launcher changed. heal_stale_hooks still
    handles foreign dead hooks afterward.
    """
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})
    if not hooks:
        return
    removed = 0
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            text = "".join(
                h.get("command", "") + h.get("prompt", "")
                for h in entry.get("hooks", [])
            )
            if any(marker in text for marker in CLEAN_RAG_OWNED_MARKERS):
                removed += 1
            else:
                kept.append(entry)
        hooks[event] = kept
    write_json(SETTINGS_PATH, settings)
    _ok(f"wiped {removed} clean-rag hook(s) for a clean reinstall")


def heal_stale_hooks() -> None:
    """Make a re-install repair a broken or stale settings.json.

    Two failure modes this fixes, both seen for real:

    1. A registration left over from an older install points at a script that no
       longer exists (research-task-nudge was the one that bit). If that command
       isn't wrapped, the missing script exits nonzero and, on a PreToolUse hook,
       blocks the tool. So any registration whose target script is gone gets
       pruned here.

    2. A hook registered before the launcher existed runs the script directly,
       so a later branch switch or deletion breaks it. Every remaining command
       gets wrapped through hook-run.py, which no-ops a missing script instead of
       breaking. Idempotent: already wrapped commands are left alone.

    Runs near the end of install, and because ClaudeBoost's setup.py delegates to
    this installer as its last step, setup.py inherits the heal for free.
    """
    settings = read_json(SETTINGS_PATH)
    hooks = settings.get("hooks", {})
    if not hooks:
        return

    pruned = 0
    wrapped = 0
    for event, entries in list(hooks.items()):
        kept = []
        for entry in entries:
            drop_entry = False
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if not cmd or ".py" not in cmd:
                    continue
                target = _hook_target_script(cmd)
                if target is not None and not target.exists():
                    # Deleted or deprecated script. Drop the whole entry so it
                    # can't fire a missing file.
                    drop_entry = True
                    pruned += 1
                    break
                new_cmd = _wrap_command(cmd)
                if new_cmd != cmd:
                    h["command"] = new_cmd
                    wrapped += 1
            if not drop_entry:
                kept.append(entry)
        hooks[event] = kept

    if pruned or wrapped:
        write_json(SETTINGS_PATH, settings)
        _ok(f"healed hooks: pruned {pruned} dead, wrapped {wrapped} through hook-run.py")
    else:
        _ok("hooks healthy: none dead, all wrapped")


def _register_hook(
    settings: dict,
    hook_type: str,
    sentinel: str,
    hook_entry: dict,
    prepend: bool = False,
    label: str = "",
) -> None:
    """Register a hook in settings.json, idempotently.

    If a hook with the sentinel already exists, refresh its command.
    Otherwise, append (or prepend) the new entry.
    """
    hooks = settings.setdefault("hooks", {})
    hook_list = hooks.get(hook_type, [])
    if not isinstance(hook_list, list):
        hook_list = []

    # Every registration funnels through here, so wrapping in this one place
    # covers hooks that don't exist yet too. clean-rag's own hooks get the
    # portable env-var launcher, not a machine-specific absolute path.
    for h in hook_entry.get("hooks", []):
        if "command" in h:
            h["command"] = _wrap_command(h["command"], runner=PORTABLE_HOOK_RUNNER)

    new_cmd = ""
    for h in hook_entry.get("hooks", []):
        if "command" in h:
            new_cmd = h["command"]
            break

    # Check if already registered
    for existing in hook_list:
        for h in existing.get("hooks", []):
            cmd = h.get("command", "")
            prompt = h.get("prompt", "")
            if sentinel in cmd or sentinel in prompt:
                # Refresh
                if new_cmd and cmd != new_cmd:
                    h["command"] = new_cmd
                    _ok(f"{label} hook path refreshed")
                elif "prompt" in h and sentinel in prompt:
                    # Refresh prompt text
                    for new_h in hook_entry.get("hooks", []):
                        if "prompt" in new_h:
                            h["prompt"] = new_h["prompt"]
                    _ok(f"{label} prompt refreshed")
                else:
                    _ok(f"{label} already registered")
                hooks[hook_type] = hook_list
                write_json(SETTINGS_PATH, settings)
                return

    if prepend:
        hook_list.insert(0, hook_entry)
    else:
        hook_list.append(hook_entry)
    hooks[hook_type] = hook_list
    write_json(SETTINGS_PATH, settings)
    _ok(f"{label} registered ({hook_type})")




# ---------------------------------------------------------------------------
# Step 3b: Register graph-context-inject hook (PreToolUse) -- plan Stage 5+7.
# Not prepend=True like proof-gate: this one only informs, never blocks, so
# order relative to proof-gate doesn't matter for correctness.
# ---------------------------------------------------------------------------
def register_graph_context_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/graph-context-inject.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", GRAPH_CONTEXT_SENTINEL,
        hook_entry, prepend=False, label="graph-context-inject",
    )


# ---------------------------------------------------------------------------
# Step 4: Set CLEAN_RAG_HOME env var in settings.json
# ---------------------------------------------------------------------------
def set_env_var() -> None:
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})
    env["CLEAN_RAG_HOME"] = CLEAN_RAG_HOME.as_posix()
    # Default proof-gate to batched (once-per-turn) checking everywhere, not
    # just for local models. proof-gate.py's own default is "pretooluse"
    # (blocks every Edit/Write/MultiEdit individually) unless this env var
    # says otherwise -- "stop" defers checking to the Stop hook instead.
    # Settings.json's env block is visible to hook subprocesses (confirmed
    # by LocalAI's manage-claude-settings.ps1, which sets this same var to
    # gate local-model burst writes), so no real OS-level env var is needed
    # here, unlike CLAUDE_CODE_AUTO_COMPACT_WINDOW which upstream Claude
    # Code's own autocompact logic can't see through settings.json.
    env.setdefault("CLEAN_RAG_GATE_MODE", "stop")
    # Compact at 60% rather than the default, so compaction happens while there
    # is still room to write a decent summary. setdefault, not assignment: a
    # number the human has already tuned is theirs to keep.
    env.setdefault("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE", "60")
    # pipe-down ships a 25 word cap and an LLM judge that spawns a claude
    # subprocess per write. setdefault, so a human who retunes either keeps it.
    env.setdefault("PIPE_DOWN_MAX_WORDS", "20")
    env.setdefault("PIPE_DOWN_LLM", "0")
    write_json(SETTINGS_PATH, settings)
    _ok(f"CLEAN_RAG_HOME set to {CLEAN_RAG_HOME.as_posix()}")
    _ok(f"Auto compact threshold {env['CLAUDE_AUTOCOMPACT_PCT_OVERRIDE']}%")


def protect_research_state() -> None:
    """Deny the Edit/Write tools on the research gate's state directory.

    Front door lock for the tamper evidence. state/research/ holds the turn
    stamps and the hash chained audit log, all machine written. Nothing has a
    legitimate reason to edit them by hand, so denying the model's Edit/Write
    tools there stops the reflexive "just write the stamp" shortcut and shows a
    block message instead, which is the moment it should spawn research instead.

    This is a speed bump, not a wall. The harness enforces deny on its own file
    tools, but a python subprocess run through Bash can still open the file, so
    a determined bypass remains. That's fine: the hash chained audit
    (cli/audit.py verify) makes any bypass permanent and greppable. Cheap lock
    plus audit, the same shape as chattr +a over an append only log. Verified
    worth keeping via /research this session (defense in depth, non adversarial
    threat model, zero false positives).

    Idempotent: adds each rule only if absent.
    """
    settings = read_json(SETTINGS_PATH)
    deny = settings.setdefault("permissions", {}).setdefault("deny", [])
    rules = [
        "Edit(**/clean-rag/state/research/**)",
        "Write(**/clean-rag/state/research/**)",
    ]
    added = 0
    for rule in rules:
        if rule not in deny:
            deny.append(rule)
            added += 1
    if added:
        write_json(SETTINGS_PATH, settings)
        _ok(f"research state protected ({added} deny rule(s) added)")
    else:
        _ok("research state deny rules already present")
    _ok("CLEAN_RAG_GATE_MODE defaulted to 'stop' (batched proof-checking once per turn)")


# ---------------------------------------------------------------------------
# Step 5: Register SessionStart — NO-OP (enforcement via UserPromptSubmit + Stop)
# ---------------------------------------------------------------------------
def register_session_prompt() -> None:
    # SessionStart: prompt-type hooks are NOT supported (SessionStart fires before any conversation)
    # Enforcement moved to:
    #   UserPromptSubmit: rag-enforce.py (real query search, web fallback, git auto index every turn)
    #   PreToolUse: code-pattern-inject.py, rag-search-on-edit.py (forced research before edits)
    # No hook registered here.
    _ok("SessionStart enforcement via UserPromptSubmit + PreToolUse hooks")


# ---------------------------------------------------------------------------
# Step 5b: Register rag-enforce UserPromptSubmit hook
# ---------------------------------------------------------------------------
def register_rag_enforce_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/rag-enforce.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "UserPromptSubmit", RAG_ENFORCE_SENTINEL,
        hook_entry, label="rag-enforce",
    )


# ---------------------------------------------------------------------------
# Step 5c: Register reindex PostToolUse hook
# ---------------------------------------------------------------------------
def register_reindex_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    # Use env var for portability across machines
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/reindex-after-edit.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", REINDEX_SENTINEL,
        hook_entry, label="reindex-after-edit",
    )


def register_verify_after_edit_hook() -> None:
    # The post write half of the gate: after code is written, nudge to verify it
    # by running a check, not by self reviewing. See verify-after-edit.py.
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/verify-after-edit.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", VERIFY_AFTER_EDIT_SENTINEL,
        hook_entry, label="verify-after-edit",
    )


def register_record_edit_hook() -> None:
    # Records which files an edit touched, so the Stop gates fire even when the
    # session cwd is not the repo being edited. See record-edit.py and
    # turn_edits.py.
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/record-edit.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", RECORD_EDIT_SENTINEL,
        hook_entry, label="record-edit",
    )


def setup_graphrag() -> None:
    """Set up the isolated GraphRAG stack: venv, fast-graphrag, and Ollama models.

    Idempotent and best effort: it skips whatever is already present and never
    aborts the install if an optional piece fails. Matches the per machine venv
    convention (these isolated venvs are built here, never committed).
    """
    import shutil
    import subprocess

    home = Path(__file__).resolve().parent
    venv = home / "graphrag-venv"
    scripts = "Scripts" if os.name == "nt" else "bin"
    venv_py = venv / scripts / ("python.exe" if os.name == "nt" else "python")

    try:
        if not venv_py.is_file():
            print("  creating graphrag-venv ...")
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] could not create graphrag-venv: {e}")
        return

    try:
        probe = subprocess.run(
            [str(venv_py), "-c", "import importlib.util as u; print(u.find_spec('fast_graphrag') is not None)"],
            capture_output=True, text=True, timeout=30,
        )
        if "True" in probe.stdout:
            print("  fast-graphrag already installed")
        else:
            print("  installing fast-graphrag into graphrag-venv (moderate download) ...")
            subprocess.run([str(venv_py), "-m", "pip", "install", "--quiet", "fast-graphrag"], check=True, timeout=600)
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] fast-graphrag install failed: {e}")

    if not shutil.which("ollama"):
        print("  [action needed] Ollama not found. Install it, then pull the models:")
        print("    ollama pull qwen2.5:7b-instruct")
        print("    ollama pull nomic-embed-text")
        return
    try:
        listed = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=15).stdout
    except Exception:  # noqa: BLE001
        listed = ""
    for model in ("qwen2.5:7b-instruct", "nomic-embed-text"):
        if model in listed:
            print(f"  {model} already pulled")
            continue
        try:
            print(f"  pulling {model} (this can be large) ...")
            subprocess.run(["ollama", "pull", model], check=True, timeout=3600)
        except Exception as e:  # noqa: BLE001
            print(f"  [warn] could not pull {model}: {e}")


def setup_clean_rag_venv() -> None:
    """Set up the isolated venv the server's embedding stack runs in.

    Creates the venv if missing, then always runs `pip install -r
    requirements.txt` against it. That call is idempotent and best effort on
    its own: pip already skips anything whose pin is already satisfied, so
    there is no need to hand roll that check.

    This used to probe for one package (sentence_transformers) and skip the
    whole install if it imported, on the theory that meant the venv was fully
    populated. That broke the moment a second dependency was added to
    requirements.txt later (textual, for cli/console.py): sentence_transformers
    still imported fine, so the probe reported "already populated" and pip
    never ran, leaving textual missing on every machine that had installed
    before that line was added. Running pip every time is what a normal
    project does (CI, Docker) for exactly this reason.

    Why the venv exists at all. The server used to import torch, transformers and
    sentence-transformers from whatever interpreter happened to launch it,
    normally the user's global one. Three packages that must agree on versions,
    installed next to everything else on the machine, is a standing conflict. It
    went wrong exactly the way that predicts: an interrupted pip run left
    huggingface_hub with no __init__.py, and transformers holding 1773 files
    from a version its own dist-info disagreed with. Every embedding load failed
    for days, and pip could not repair it because the metadata recording what to
    delete was itself wrong. A venv is the fix that generalises, rather than
    repairing one machine by hand.

    The pins live in requirements.txt. They are exact for the three packages
    that broke, because a loose range is what let the versions drift apart with
    nothing to catch it.
    """
    import subprocess

    home = Path(__file__).resolve().parent
    venv = home / "clean-rag-venv"
    scripts = "Scripts" if os.name == "nt" else "bin"
    venv_py = venv / scripts / ("python.exe" if os.name == "nt" else "python")
    reqs = home / "requirements.txt"

    try:
        if not venv_py.is_file():
            print("  creating clean-rag-venv ...")
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        print(f"  [skip] could not create clean-rag-venv: {e}")
        return

    if not reqs.is_file():
        print(f"  [skip] no requirements.txt at {reqs}")
        return

    try:
        # torch alone is a few hundred MB, so a first run is the slow step of
        # the whole install. Long timeout on purpose: a half installed venv is
        # the state this function exists to avoid creating. A re-run with
        # everything already satisfied is fast, pip just checks each pin.
        print("  installing requirements into clean-rag-venv ...")
        subprocess.run(
            [str(venv_py), "-m", "pip", "install", "--quiet", "-r", str(reqs)],
            check=True, timeout=3600,
        )
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] clean-rag-venv requirements install failed: {e}")
        print("  the server falls back to the launching interpreter, which may be broken")


# ---------------------------------------------------------------------------
# Step 5g: Register spec-compliance-gate hook (Stop) -- checks task keywords
# ---------------------------------------------------------------------------
def register_spec_compliance_gate_hook() -> None:
    """Register the spec-compliance Stop hook.

    Always registered, default on -- cheap (regex only, no LLM call) with
    no false-block risk beyond the fixed keyword list in
    scripts/spec-compliance-gate.py. Checks whether a technology named in
    the task prompt (react, vue, typescript, etc.) shows up anywhere in
    the files changed this session; proof-gate.py has no equivalent check
    since it only verifies edits are research-backed, not that they
    satisfy what was actually asked for.
    """
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/scripts/spec-compliance-gate.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "Stop", SPEC_COMPLIANCE_GATE_SENTINEL,
        hook_entry, label="spec-compliance-gate",
    )


# ---------------------------------------------------------------------------
# Step 5h: register the autotest gate Stop hook, the execution feedback loop.
# When code changed this turn, it runs the project's tests and blocks the stop
# once on a real failure so the model fixes from the actual output. Loop safe:
# it honors stop_hook_active and caps blocks per session.
# ---------------------------------------------------------------------------
def register_auto_test_gate_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/auto-test-gate.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "Stop", AUTO_TEST_GATE_SENTINEL,
        hook_entry, label="auto-test-gate",
    )


# ---------------------------------------------------------------------------
# Step 5h2: register the verifier gate Stop hook. On a high stakes diff (auth,
# money, SQL, subprocess, concurrency) it nudges the main agent to spawn the
# fresh verifier-agent, after the tests pass. Same loop safe shape as the test
# gate: stop_hook_active guard, per session block cap, fail open.
# ---------------------------------------------------------------------------
def register_verifier_gate_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/verifier-gate.py"'
    hook_entry = {
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "Stop", VERIFIER_GATE_SENTINEL,
        hook_entry, label="verifier-gate",
    )


# ---------------------------------------------------------------------------
# The other half of the verifier gate: stamps the session record when
# verifier-agent finishes. Mirrors register_research_record_hook exactly, one
# level down (verifier_state instead of research_state). Without this the gate
# has nothing to check and blocks every stop until the cap gives up.
# ---------------------------------------------------------------------------
def register_verifier_record_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/verifier-record.py"'
    hook_entry = {
        "matcher": "Task|Agent",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", VERIFIER_RECORD_SENTINEL,
        hook_entry, label="verifier-record",
    )


# ---------------------------------------------------------------------------
# Lint gate: PostToolUse nudge that runs ruff/eslint after code writes.
# Always exits 0, reports to stderr. Not a blocker.
# ---------------------------------------------------------------------------
def register_lint_gate_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/lint-gate.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", LINT_GATE_SENTINEL,
        hook_entry, label="lint-gate",
    )


# ---------------------------------------------------------------------------
# Step 5i: Configure web search env vars
# ---------------------------------------------------------------------------
def configure_web_search_env() -> None:
    """Set web search configuration env vars in settings.json."""
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})

    env.setdefault("CLEAN_RAG_WEB_SEARCH", "true")
    env.setdefault("CLEAN_RAG_WEB_SEARCH_TIMEOUT", "4.0")
    env.setdefault("CLEAN_RAG_WEB_SEARCH_MAX_RESULTS", "3")
    env.setdefault("CLEAN_RAG_WEB_SEARCH_THRESHOLD", "0.4")

    write_json(SETTINGS_PATH, settings)
    _ok("Web search env vars configured (can be overridden in settings.json)")


# ---------------------------------------------------------------------------
# Step 5k: Configure metrics env vars
# ---------------------------------------------------------------------------
def configure_metrics_env() -> None:
    """Set code quality metrics configuration env vars in settings.json.

    METRICS_CACHE_DIR/TTL are genuinely used by server/metrics.py (real,
    working code behind the code_metrics MCP tool). CLEAN_RAG_METRICS_INJECT
    itself has no remaining consumer — metrics_inject.py was dead code
    (wrong hook signature, confirmed to never actually run) and has been
    removed; git-root auto-index detection was folded into rag-enforce.py.
    """
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})

    env.setdefault("METRICS_CACHE_DIR", "state/metrics-cache")
    env.setdefault("METRICS_CACHE_TTL", "3600")

    write_json(SETTINGS_PATH, settings)
    _ok("Metrics env vars configured (can be overridden in settings.json)")


# ---------------------------------------------------------------------------
# Step 5m: Register code pattern inject hook (PreToolUse) — enforce on Claude
# ---------------------------------------------------------------------------
def register_code_pattern_inject_hook() -> None:
    """Register hook to enforce pattern detection + research before edits.

    This blocks CLAUDE from editing without automatic pattern detection
    and research injection. Non-blocking in background threads.
    """
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/code-pattern-inject.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", CODE_PATTERN_INJECT_SENTINEL,
        hook_entry, label="code-pattern-inject",
    )


# ---------------------------------------------------------------------------
# The research gate. Nudges when no researcher or swiper run this session has
# declared that it covered this file. It does not block: every return in
# hooks/research-gate.py's main() is 0, by decision, because an unresearched
# edit is recoverable and earns an audit trail rather than a refusal.
#
# Prepended so its stderr note lands before the other pre edit hooks add their
# own output, not because it refuses anything.
# ---------------------------------------------------------------------------
def register_research_gate_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/research-gate.py"'
    hook_entry = {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", RESEARCH_GATE_SENTINEL,
        hook_entry, prepend=True, label="research-gate",
    )


# ---------------------------------------------------------------------------
# The other half of the pre edit gate: catch a code file written through the
# shell (echo >, tee, sed -i, python open), which the Edit/Write matcher never
# sees. Same rule, applied to Bash. Closes Claude Code issue #29709.
# ---------------------------------------------------------------------------
def register_research_gate_bash_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/research-gate-bash.py"'
    hook_entry = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PreToolUse", RESEARCH_GATE_BASH_SENTINEL,
        hook_entry, label="research-gate-bash",
    )


# ---------------------------------------------------------------------------
# The other half of the gate: stamps the turn record when research-agent
# finishes. Without this the gate has nothing to check and blocks everything, so
# the two are useless apart.
# ---------------------------------------------------------------------------
def register_research_record_hook() -> None:
    settings = read_json(SETTINGS_PATH)
    hook_command = 'python "$CLEAN_RAG_HOME/hooks/research-record.py"'
    hook_entry = {
        "matcher": "Task|Agent",
        "hooks": [{"type": "command", "command": hook_command}],
    }
    _register_hook(
        settings, "PostToolUse", RESEARCH_RECORD_SENTINEL,
        hook_entry, label="research-record",
    )


# ---------------------------------------------------------------------------
# Step 5n: Configure code pattern injection environment
# ---------------------------------------------------------------------------
def configure_code_pattern_inject_env() -> None:
    """Enable pattern-based research injection on all Claude edits."""
    settings = read_json(SETTINGS_PATH)
    env = settings.setdefault("env", {})
    env.setdefault("CLEAN_RAG_PATTERN_INJECT", "true")
    write_json(SETTINGS_PATH, settings)
    _ok("Code pattern injection enabled (CLEAN_RAG_PATTERN_INJECT=true)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Install clean-rag")
    parser.add_argument("--skip-deps", action="store_true",
                        help="Skip pip install")
    args = parser.parse_args()

    print("=" * 60)
    print("clean-rag installer")
    print("=" * 60)
    print()

    # Step 1
    print("Step 1: Creating directories...")
    ensure_directories()
    ensure_env_file()

    # Step 1b
    print("\nStep 1b: Installing agents, skills, and the hook launcher into ~/.claude...")
    install_user_assets()

    # Step 2
    if not args.skip_deps:
        print("\nStep 2: Installing dependencies...")
        install_deps()
    else:
        print("\nStep 2: Skipped (--skip-deps)")

    # Step 2b
    if not args.skip_deps:
        print("\nStep 2b: Installing npm QA tools...")
        install_npm_qa_tools()
    else:
        print("\nStep 2b: Skipped (--skip-deps)")

    # Step 2b2
    if not args.skip_deps:
        print("\nStep 2b2: Registering debugging MCP servers...")
        register_mcp_servers()
    else:
        print("\nStep 2b2: Skipped (--skip-deps)")

    # Step 2b3
    if not args.skip_deps:
        print("\nStep 2b3: Installing Claude Code plugins...")
        install_plugins()
    else:
        print("\nStep 2b3: Skipped (--skip-deps)")

    # Step 2c
    if not args.skip_deps:
        print("\nStep 2c: Installing deck tooling for the powerpoint skill...")
        install_pptx_tools()
    else:
        print("\nStep 2c: Skipped (--skip-deps)")

    # Step 3
    print("\nStep 3: Registering the research gate...")
    wipe_clean_rag_hooks()  # clean slate: drop clean-rag's own hooks, then rebuild them all
    register_research_gate_hook()
    register_research_gate_bash_hook()
    register_research_record_hook()

    # Step 3b
    print("\nStep 3b: Registering graph-context-inject hook...")
    register_graph_context_hook()

    # Step 4
    print("\nStep 4: Setting environment variables...")
    set_env_var()
    protect_research_state()

    # Step 5
    print("\nStep 5: Registering session prompt...")
    register_session_prompt()

    # Step 5b
    print("\nStep 5b: Registering rag-enforce hook...")
    register_rag_enforce_hook()

    # Step 5c
    print("\nStep 5c: Registering reindex hook...")
    register_reindex_hook()
    register_verify_after_edit_hook()
    register_record_edit_hook()

    # Step 5c2. Before GraphRAG on purpose: this is the venv the server itself
    # runs in, so nothing else works until it exists.
    print("\nStep 5c2: Setting up clean-rag's own venv (large download)...")
    setup_clean_rag_venv()

    # Step 5d
    print("\nStep 5d: Setting up GraphRAG (isolated venv + models; may download)...")
    setup_graphrag()

    # Step 5f
    print("\nStep 5f: Registering spec-compliance-gate hook...")
    register_spec_compliance_gate_hook()

    # Step 5h
    print("\nStep 5h: Registering auto-test-gate hook...")
    register_auto_test_gate_hook()

    # Step 5h2
    print("\nStep 5h2: Registering verifier-gate hook...")
    register_verifier_gate_hook()
    register_verifier_record_hook()

    print("\nRegistering lint-gate hook...")
    register_lint_gate_hook()

    # Step 5i
    print("\nStep 5i: Configuring web search environment variables...")
    configure_web_search_env()

    # Step 5k
    print("\nStep 5k: Configuring metrics environment variables...")
    configure_metrics_env()

    # Step 5m
    print("\nStep 5m: Registering code-pattern-inject hook (enforce on Claude)...")
    register_code_pattern_inject_hook()

    # Step 5n
    print("\nStep 5n: Configuring code pattern injection environment...")
    configure_code_pattern_inject_env()

    # Step 6: heal a stale settings.json from an older install. Runs LAST so it
    # sees every hook this run registered, prunes any that point at a deleted
    # script, and wraps the rest through hook-run.py. This is what stops a
    # re-install inheriting a broken hook (research-task-nudge was the real one).
    print("\nStep 6: Healing hook registrations...")
    heal_stale_hooks()

    print()
    print("=" * 60)
    print("clean-rag installed successfully!")
    print()
    print(f"  Home:    {CLEAN_RAG_HOME}")
    print(f"  Hooks:")
    print(f"    PreToolUse:        graph-context-inject.py (auto-fetches caller context)")
    print(f"    PreToolUse:        code-pattern-inject.py (forces research on Edit/Write/MultiEdit)")
    print(f"    UserPromptSubmit:  rag-enforce.py (real-query search, web fallback, git auto-index)")
    print(f"    PostToolUse:       reindex-after-edit.py (keeps index fresh)")
    print(f"  Server:  python {CLEAN_RAG_HOME.as_posix()}/cli/server_ctl.py start")
    print(f"  Console: python {CLEAN_RAG_HOME.as_posix()}/cli/console.py")
    print()
    print("Start the server to enable RAG-backed research and code quality metrics injection.")
    print("=" * 60)


if __name__ == "__main__":
    main()
