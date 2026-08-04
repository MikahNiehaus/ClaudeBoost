"""Every MCP tool an agent enumerates must come from a server the installer registers.

The bug this exists to prevent: bad-cop's frontmatter listed four
mcp__test-coverage__* tools for months while setup.py registered only
mcp-debugger and playwright. Claude Code does not error on an unknown tool
name, it just silently omits it, so bad-cop believed it had coverage data and
never did. Nothing caught it because nothing cross-checked the two lists.

test_every_enumerated_server_is_registered is that cross-check.
"""
import importlib.util
import re
import subprocess
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Files that enumerate MCP tools, and the frontmatter key each uses.
TOOL_CONSUMERS = {
    "clean-rag/portable/agents/bad-cop.md": "tools",
    "clean-rag/portable/agents/good-cop.md": "tools",
    ".claude/commands/qa.md": "allowed-tools",
    ".claude/commands/debug.md": "allowed-tools",
}

# Registered outside the MCP_SERVERS tables: mdb is cloned conditionally by
# setup.py's _mdb_mcp_server, so it is legitimately absent from the npx table.
CONDITIONALLY_REGISTERED = {"mdb"}


def _load(rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(rel.replace("/", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _enumerated_tools(rel, key):
    text = (ROOT / rel).read_text(encoding="utf-8")
    # Regex rather than a YAML parse: qa.md's argument-hint uses unquoted
    # brackets that strict YAML rejects but Claude Code accepts.
    match = re.search(rf"^{key}: (.+)$", text, re.MULTILINE)
    assert match, f"{rel} has no '{key}:' frontmatter line"
    return [t.strip() for t in match.group(1).split(",") if t.strip()]


def _servers_in(rel, key):
    return {t.split("__")[1] for t in _enumerated_tools(rel, key) if t.startswith("mcp__")}


@pytest.fixture(scope="module")
def setup_mod():
    return _load("scripts/setup.py")


@pytest.fixture(scope="module")
def cleanrag_mod():
    return _load("clean-rag/install.py")


@pytest.mark.parametrize("rel,key", TOOL_CONSUMERS.items())
def test_every_enumerated_server_is_registered(rel, key, setup_mod):
    """The regression test for the test-coverage bug. Do not weaken this."""
    registered = {s["name"] for s in setup_mod.MCP_SERVERS} | CONDITIONALLY_REGISTERED
    used = _servers_in(rel, key)
    orphans = used - registered
    assert not orphans, (
        f"{rel} enumerates tools from {sorted(orphans)}, which no installer "
        f"registers. Those tools silently will not exist at runtime. Either add "
        f"the server to MCP_SERVERS in scripts/setup.py and clean-rag/install.py, "
        f"or drop its tools from the frontmatter."
    )


@pytest.mark.parametrize("rel,key", TOOL_CONSUMERS.items())
def test_no_wildcards_in_tool_lists(rel, key):
    """Claude Code shows `mcp__server__*` as Unrecognized and drops the tools."""
    for tool in _enumerated_tools(rel, key):
        assert "*" not in tool, f"{rel}: wildcard {tool!r} is silently ignored by Claude Code"


@pytest.mark.parametrize("rel,key", TOOL_CONSUMERS.items())
def test_tool_names_well_formed_and_unique(rel, key):
    tools = _enumerated_tools(rel, key)
    dupes = sorted({t for t in tools if tools.count(t) > 1})
    assert not dupes, f"{rel}: duplicate tools {dupes}"
    for tool in tools:
        if tool.startswith("mcp__"):
            parts = tool.split("__")
            assert len(parts) == 3 and all(parts), f"{rel}: malformed tool name {tool!r}"


def test_installer_tables_agree(setup_mod, cleanrag_mod):
    """clean-rag installs standalone, so it carries its own copy of the table.

    Two copies drift. This is what notices.
    """
    boost = {s["name"]: s["args"] for s in setup_mod.MCP_SERVERS}
    portable = dict(cleanrag_mod.MCP_SERVERS)
    assert boost == portable, (
        "scripts/setup.py and clean-rag/install.py disagree on the MCP server "
        f"table.\n  setup.py: {boost}\n  clean-rag: {portable}"
    )


def test_setup_registration_is_idempotent(setup_mod, monkeypatch):
    """A second install must not re-add servers that are already there."""
    calls = []

    def fake_run(args):
        calls.append(args)
        return 0, ""

    monkeypatch.setattr(setup_mod, "run_cmd", fake_run)
    listed = "\n".join(f"{s['name']}: ... - Connected" for s in setup_mod.MCP_SERVERS)
    for server in setup_mod.MCP_SERVERS:
        setup_mod._register_one(["claude"], listed, server)

    assert not [c for c in calls if "add" in c], (
        f"re-added already-registered servers: {calls}")


def test_setup_registers_missing_servers(setup_mod, monkeypatch):
    """The other half: a server absent from the list actually does get added."""
    calls = []
    monkeypatch.setattr(setup_mod, "run_cmd", lambda args: (calls.append(args), (0, ""))[1])
    for server in setup_mod.MCP_SERVERS:
        setup_mod._register_one(["claude"], "", server)

    added = [c[c.index("add") + 1] for c in calls if "add" in c]
    assert added == [s["name"] for s in setup_mod.MCP_SERVERS], (
        f"not every missing server was registered: {added}")


def test_missing_runtime_skips_without_raising(setup_mod, monkeypatch):
    """No npx must degrade the debugging surface, never break the install."""
    calls = []
    monkeypatch.setattr(setup_mod, "run_cmd", lambda args: (calls.append(args), (0, ""))[1])
    monkeypatch.setattr(setup_mod.shutil, "which", lambda name: None)

    setup_mod._register_one(["claude"], "", setup_mod.MCP_SERVERS[0])
    assert not calls, "attempted registration with the required runtime missing"


def test_cleanrag_registration_survives_a_failing_claude_cli(cleanrag_mod, monkeypatch):
    """`claude mcp list` blowing up must not abort the clean-rag install."""
    def boom(*a, **kw):
        raise OSError("simulated")

    monkeypatch.setattr(cleanrag_mod, "shutil", types.SimpleNamespace(
        which=lambda name: "C:/fake/" + name))
    monkeypatch.setattr(cleanrag_mod, "subprocess", types.SimpleNamespace(run=boom))

    cleanrag_mod.register_mcp_servers()  # must not raise


def test_debugging_methodology_skill_ships_portable():
    """The skill is the single source for technique selection.

    It lives under portable/skills because clean-rag/install.py copytrees that
    directory wholesale, which is what makes it portable with no installer change.
    """
    skill = ROOT / "clean-rag/portable/skills/debugging-methodology/SKILL.md"
    assert skill.is_file(), "debugging-methodology skill is missing"

    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---\n"), "skill has no frontmatter"
    assert re.search(r"^name: debugging-methodology$", text, re.MULTILINE)
    assert re.search(r"^description: .+", text, re.MULTILINE)

    # The techniques the consumers name must actually be documented here.
    for technique in ("git bisect", "Delta debugging", "Differential debugging",
                      "Record-replay", "Binary search on state"):
        assert technique.lower() in text.lower(), f"skill does not cover {technique}"

    # The database rule is the one hard prohibition in the skill.
    assert "do not execute against a live database" in text.lower()
    assert "ssms" in text.lower()


@pytest.mark.parametrize("rel,key", TOOL_CONSUMERS.items())
def test_consumers_point_at_the_methodology_skill(rel, key):
    """Enumerating the tools is half of it; knowing which to reach for is the rest."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert "debugging-methodology" in text, (
        f"{rel} enumerates debugging tools but never points at the "
        f"debugging-methodology skill, so it has no technique guidance")
