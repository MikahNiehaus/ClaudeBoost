"""Every MCP tool an agent enumerates must come from a server the installer registers.

The bug this exists to prevent: bad-cop's frontmatter listed four
mcp__test-coverage__* tools for months while setup.py registered only
mcp-debugger and playwright. Claude Code does not error on an unknown tool
name, it just silently omits it, so bad-cop believed it had coverage data and
never did. Nothing caught it because nothing cross-checked the two lists.

test_every_enumerated_server_is_registered is that cross-check.
"""
# `X | None` in a signature below is evaluated at def time without this, which
# cannot import on the 3.9 floor clean-rag/tests/test_python_floor_compatibility.py
# holds the repo to.
from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Files that enumerate DEBUGGING MCP tools. These also have to point at the
# debugging-methodology skill, since enumerating a debugger is half of it and
# knowing which technique to reach for is the rest.
TOOL_CONSUMERS = {
    "clean-rag/portable/agents/bad-cop.md": "tools",
    "clean-rag/portable/agents/good-cop.md": "tools",
    ".claude/commands/qa.md": "allowed-tools",
    ".claude/commands/debug.md": "allowed-tools",
}

# Every file that enumerates any MCP tool at all. researcher and swiper carry
# research servers rather than debuggers, so they are exempt from the
# methodology check but NOT from the one that matters most: a tool whose server
# nobody registers silently does not exist at runtime.
ALL_TOOL_CONSUMERS = {
    **TOOL_CONSUMERS,
    "clean-rag/portable/agents/researcher.md": "tools",
    "clean-rag/portable/agents/swiper.md": "tools",
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


@pytest.mark.parametrize("rel,key", ALL_TOOL_CONSUMERS.items())
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


@pytest.mark.parametrize("rel,key", ALL_TOOL_CONSUMERS.items())
def test_no_wildcards_in_tool_lists(rel, key):
    """Claude Code shows `mcp__server__*` as Unrecognized and drops the tools."""
    for tool in _enumerated_tools(rel, key):
        assert "*" not in tool, f"{rel}: wildcard {tool!r} is silently ignored by Claude Code"


@pytest.mark.parametrize("rel,key", ALL_TOOL_CONSUMERS.items())
def test_tool_names_well_formed_and_unique(rel, key):
    tools = _enumerated_tools(rel, key)
    dupes = sorted({t for t in tools if tools.count(t) > 1})
    assert not dupes, f"{rel}: duplicate tools {dupes}"
    for tool in tools:
        if tool.startswith("mcp__"):
            parts = tool.split("__")
            assert len(parts) == 3 and all(parts), f"{rel}: malformed tool name {tool!r}"


# Keys that change what actually gets registered. label, hint and why are
# presentation and live only in scripts/setup.py, so comparing whole rows would
# fail on a difference that cannot affect any install.
FUNCTIONAL_KEYS = ("args", "needs", "needs_env", "transport", "url", "headers", "env")


def _functional(server: dict) -> dict:
    return {k: server[k] for k in FUNCTIONAL_KEYS if k in server}


def test_installer_tables_agree(setup_mod, cleanrag_mod):
    """clean-rag installs standalone, so it carries its own copy of the table.

    Two copies drift. This is what notices.

    Compares every key that changes the registration, not just args. args alone
    was enough while every row was a bare stdio npx package; it stopped being
    enough once rows carried a transport, a URL, a header and a required env
    var, because two tables could then agree on args while registering
    genuinely different servers.
    """
    boost = {s["name"]: _functional(s) for s in setup_mod.MCP_SERVERS}
    portable = {s["name"]: _functional(s) for s in cleanrag_mod.MCP_SERVERS}
    assert boost == portable, (
        "scripts/setup.py and clean-rag/install.py disagree on the MCP server "
        f"table.\n  setup.py: {boost}\n  clean-rag: {portable}"
    )


def test_setup_registration_is_idempotent(setup_mod, monkeypatch):
    """A second install must not re-add servers that are already there.

    Every prerequisite and credential is faked present, which is the whole
    point. Reading the real shutil.which and the real os.environ meant that on
    any machine without uvx or a GitHub token, seven of the fifteen rows
    returned at the prerequisite check and never reached the "already
    registered" guard this test exists to verify. Deleting that guard outright
    left the test green for those seven. A fresh dev machine or a CI runner is
    exactly that machine, so the gap was the normal case, not an edge one.
    """
    calls = []

    def fake_run(args):
        calls.append(args)
        return 0, ""

    monkeypatch.setattr(setup_mod, "run_cmd", fake_run)
    monkeypatch.setattr(setup_mod, "resolve_tool", lambda name: "/fake/" + name)
    monkeypatch.setattr(setup_mod.os, "environ", {
        s["needs_env"]: "fake-value"
        for s in setup_mod.MCP_SERVERS if s.get("needs_env")
    })
    listed = "\n".join(f"{s['name']}: ... - Connected" for s in setup_mod.MCP_SERVERS)
    for server in setup_mod.MCP_SERVERS:
        setup_mod._register_one(["claude"], listed, server)

    assert not [c for c in calls if _registered_name(c)], (
        f"re-added already-registered servers: {calls}")


def _registered_name(cmd: list[str]) -> str | None:
    """The server name out of an `mcp add` or `mcp add-json` command, or None.

    Both verbs put the name immediately after themselves. Matching on "add"
    alone misses add-json entirely, which silently dropped every credentialed
    and remote server from this assertion.
    """
    for verb in ("add", "add-json"):
        if verb in cmd:
            return cmd[cmd.index(verb) + 1]
    return None


def test_setup_registers_missing_servers(setup_mod, monkeypatch):
    """The other half: a server absent from the list actually does get added.

    Every prerequisite is faked present. The point here is that the loop
    reaches every row, not whether this machine happens to have uvx or a
    GitHub token; the skip paths have their own tests below.
    """
    calls = []
    monkeypatch.setattr(setup_mod, "run_cmd", lambda args: (calls.append(args), (0, ""))[1])
    monkeypatch.setattr(setup_mod, "resolve_tool", lambda name: "C:/fake/" + name)
    monkeypatch.setattr(setup_mod.os, "environ", {
        s["needs_env"]: "fake-value"
        for s in setup_mod.MCP_SERVERS if s.get("needs_env")
    })
    for server in setup_mod.MCP_SERVERS:
        setup_mod._register_one(["claude"], "", server)

    added = [n for n in (_registered_name(c) for c in calls) if n]
    assert added == [s["name"] for s in setup_mod.MCP_SERVERS], (
        f"not every missing server was registered: {added}")


def test_missing_credential_skips_without_raising(setup_mod, monkeypatch):
    """An unset credential skips that one server, it never fails the install.

    Same posture as the missing-executable path: the install degrades, so a
    user without a GitHub token still gets every other server.
    """
    credentialed = [s for s in setup_mod.MCP_SERVERS if s.get("needs_env")]
    assert credentialed, "no server declares needs_env; this test guards nothing"

    calls = []
    monkeypatch.setattr(setup_mod, "run_cmd", lambda args: (calls.append(args), (0, ""))[1])
    monkeypatch.setattr(setup_mod, "resolve_tool", lambda name: "C:/fake/" + name)
    monkeypatch.setattr(setup_mod.os, "environ", {})

    for server in credentialed:
        setup_mod._register_one(["claude"], "", server)
    assert not calls, f"registered a server whose credential was unset: {calls}"


def test_credential_is_a_placeholder_never_a_literal_secret(setup_mod):
    """The token must reach the server as ${VAR}, expanded by Claude Code.

    Resolving it at install time would write the real secret into
    ~/.claude.json in plaintext. This asserts we never do that.
    """
    import os as _os
    marker = "SHOULD-NEVER-BE-INLINED"
    for server in setup_mod.MCP_SERVERS:
        env_var = server.get("needs_env")
        if not env_var:
            continue
        payload = setup_mod._server_json(server)
        assert marker not in payload
        if server.get("headers") or server.get("env"):
            assert "${" + env_var + "}" in payload, (
                f"{server['name']} does not pass {env_var} as a ${{}} placeholder: "
                f"{payload}")
        # And the real ambient value, whatever it is, must not appear either.
        real = _os.environ.get(env_var)
        if real:
            assert real not in payload, (
                f"{server['name']} inlined the real {env_var} value into its "
                f"registration payload")


def test_missing_runtime_skips_without_raising(setup_mod, monkeypatch):
    """No npx must degrade the debugging surface, never break the install."""
    calls = []
    monkeypatch.setattr(setup_mod, "run_cmd", lambda args: (calls.append(args), (0, ""))[1])
    monkeypatch.setattr(setup_mod, "resolve_tool", lambda name: None)

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


# --- The two installers must not diverge in control flow either -------------
#
# test_installer_tables_agree compares the MCP_SERVERS rows. It cannot see the
# code around them, and that is where the real divergence was: setup.py checked
# prerequisites before the "already registered" status, clean-rag/install.py
# checked status first. Same machine, same server, two different answers, with
# both tables in perfect agreement.

# Every combination that reaches a different branch, as (status, has_tool,
# has_cred). status None means "not registered yet".
_SCENARIOS = [
    (status, has_tool, has_cred)
    for status in (None, "Connected", "Failed to connect")
    for has_tool in (True, False)
    for has_cred in (True, False)
]


def _env_for(servers, has_cred):
    if not has_cred:
        return {}
    return {s["needs_env"]: "v" for s in servers if s.get("needs_env")}


def _listed_output(servers, status):
    """`claude mcp list` stdout with every server present at `status`."""
    if status is None:
        return "Checking MCP server health...\n"
    return "\n".join(f"{s['name']}: some-command - {status}" for s in servers)


def _spy_on_decisions(mod, monkeypatch):
    """Record every (server, action) the module's real code path decides.

    Wraps registration_action rather than reading log output, because the two
    installers word their warnings differently on purpose. The decision is the
    thing that has to match; the phrasing is not.
    """
    decisions = []
    real = mod.registration_action

    def spy(server, status, resolve, environ):
        result = real(server, status, resolve, environ)
        decisions.append((server["name"], result[0], result[1]))
        return result

    monkeypatch.setattr(mod, "registration_action", spy)
    return decisions


def _setup_decisions(setup_mod, monkeypatch, status, has_tool, has_cred):
    decisions = _spy_on_decisions(setup_mod, monkeypatch)
    monkeypatch.setattr(setup_mod, "run_cmd", lambda a: (0, ""))
    monkeypatch.setattr(setup_mod, "resolve_tool",
                        lambda n: "/fake/" + n if has_tool else None)
    monkeypatch.setattr(setup_mod.os, "environ",
                        _env_for(setup_mod.MCP_SERVERS, has_cred))
    listed = _listed_output(setup_mod.MCP_SERVERS, status)
    for server in setup_mod.MCP_SERVERS:
        setup_mod._register_one(["claude"], listed, server)
    return decisions


def _cleanrag_decisions(cleanrag_mod, monkeypatch, status, has_tool, has_cred):
    """Drives the real register_mcp_servers loop, not the pure function.

    The divergence this exists for lived in the loop, so the loop is what has
    to run. A loop that stops consulting registration_action records nothing
    for the rows it short circuits, which is exactly the failure.
    """
    decisions = _spy_on_decisions(cleanrag_mod, monkeypatch)
    listed = _listed_output(cleanrag_mod.MCP_SERVERS, status)

    def fake_run(args, **kwargs):
        if "list" in args:
            return types.SimpleNamespace(returncode=0, stdout=listed, stderr="")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(cleanrag_mod, "_claude_cmd", lambda: ["claude"])
    monkeypatch.setattr(cleanrag_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(cleanrag_mod, "resolve_tool",
                        lambda n: "/fake/" + n if has_tool else None)
    monkeypatch.setattr(cleanrag_mod.os, "environ",
                        _env_for(cleanrag_mod.MCP_SERVERS, has_cred))
    cleanrag_mod.register_mcp_servers()
    return decisions


@pytest.mark.parametrize("status,has_tool,has_cred", _SCENARIOS)
def test_installers_agree_on_every_registration_decision(
        setup_mod, cleanrag_mod, monkeypatch, status, has_tool, has_cred):
    """The control-flow twin of test_installer_tables_agree.

    Runs both installers' real code paths over the same machine state and
    compares the decision each reaches for each server. Comparing only what
    got registered is not enough: for an already registered server with a
    missing credential neither installer registers anything, and they still
    disagree about why, which is the bug that was shipped.
    """
    boost = _setup_decisions(setup_mod, monkeypatch, status, has_tool, has_cred)
    portable = _cleanrag_decisions(cleanrag_mod, monkeypatch, status, has_tool, has_cred)
    assert boost == portable, (
        f"for status={status!r} tool={has_tool} cred={has_cred} the installers "
        f"decided differently.\n  setup.py:  {boost}\n  clean-rag: {portable}")


def test_a_missing_credential_is_reported_even_when_already_registered(setup_mod):
    """Order is the contract, and this is the case that pins it down.

    Claude Code expands ${VAR} from its own environment when it launches, so a
    server that is already registered but whose credential is unset still
    sends the literal "${VAR}" as its token and fails at runtime. Reporting
    "already registered" here would hide a broken server behind a tick.
    """
    github = next(s for s in setup_mod.MCP_SERVERS if s["name"] == "github")
    action, detail = setup_mod.registration_action(
        github, "Connected", lambda _n: "/fake/tool", {})
    assert action == "skip-missing-credential", (
        f"an already registered server with no credential reported {action!r}")
    assert detail == "GITHUB_MCP_TOKEN"


# --- The injection boundary, as a check rather than a paragraph -------------

# Servers that read untrusted content off the network. A reviewer holding one
# of these can be argued out of a finding by the thing it is reviewing, which
# is why bad-cop and good-cop never had WebFetch either.
FETCH_SHAPED_SERVERS = {"context7", "arxiv", "socket", "github", "atlassian"}

REVIEWER_AGENTS = (
    "clean-rag/portable/agents/bad-cop.md",
    "clean-rag/portable/agents/good-cop.md",
)


@pytest.mark.parametrize("rel", REVIEWER_AGENTS)
def test_reviewers_get_no_fetch_shaped_tools(rel):
    leaked = sorted(_servers_in(rel, "tools") & FETCH_SHAPED_SERVERS)
    assert not leaked, (
        f"{rel} enumerates tools from fetch-shaped server(s) {leaked}. A "
        f"reviewer that reads untrusted network content can be talked out of "
        f"a finding; route those to researcher and swiper instead.")


@pytest.mark.parametrize("rel", REVIEWER_AGENTS)
def test_reviewers_have_no_webfetch(rel):
    """The same boundary, one layer down from the MCP servers."""
    assert "WebFetch" not in _enumerated_tools(rel, "tools"), (
        f"{rel} has WebFetch, which is the exposure the MCP routing above "
        f"exists to avoid")


# --- Portability ------------------------------------------------------------

def test_resolve_tool_finds_a_script_dir_executable(setup_mod, tmp_path, monkeypatch):
    """A console script off PATH must still resolve.

    `pip install uv` puts uv.exe and uvx.exe in a per-user Scripts directory
    that a default Windows install does not put on PATH, so shutil.which alone
    called four servers missing while the executable was sitting right there.
    """
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    exe = scripts / ("uvx.exe" if os.name == "nt" else "uvx")
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)

    monkeypatch.setattr(setup_mod.shutil, "which", _only_on_explicit_path)
    monkeypatch.setattr(setup_mod, "_script_dirs", lambda: [str(scripts)])
    assert setup_mod.resolve_tool("uvx"), (
        "resolve_tool missed an executable in the interpreter's script dir")
    assert setup_mod.resolve_tool("definitely-not-installed") is None


_REAL_WHICH = shutil.which


def _only_on_explicit_path(name, mode=os.F_OK | os.X_OK, path=None):
    """shutil.which with the ambient PATH removed, so the test is hermetic.

    Binds the real function at import time. Reading shutil.which at call time
    would find the monkeypatched one, which is this function.
    """
    if path is None:
        return None
    return _REAL_WHICH(name, mode=mode, path=path)


def _function_source(rel, name):
    src = (ROOT / rel).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{rel} has no function {name}")


def test_registration_action_twin_is_byte_identical():
    """Both copies claim to be byte-identical, so make that claim checkable.

    They were not: the bodies matched but only setup.py's carried annotations.
    A comment asserting something no test confirms is how the installers
    diverged in the first place.
    """
    boost = _function_source("scripts/setup.py", "registration_action")
    portable = _function_source("clean-rag/install.py", "registration_action")
    assert boost == portable, (
        "registration_action differs between the two installers.\n"
        f"  setup.py:\n{boost}\n  clean-rag:\n{portable}")


def test_mcp_names_from_table_raises_rather_than_returning_nothing(tmp_path):
    """An empty result must reach the fallback, not pass as a real answer.

    _shared_mcp_names only falls back on an exception, so a silent empty list
    would make --purge deregister nothing but "mdb".
    """
    uninstall = _load("scripts/uninstall.py")
    shapes = {
        "empty literal": "MCP_SERVERS: list[dict] = []\n",
        "built by a call": "MCP_SERVERS = build_table()\n",
        "comprehension": "MCP_SERVERS = [r for r in rows]\n",
        "absent": "SOMETHING_ELSE = 1\n",
    }
    for label, src in shapes.items():
        path = tmp_path / "setup.py"
        path.write_text(src, encoding="utf-8")
        try:
            result = uninstall._mcp_names_from_table(path)
        except Exception:
            continue
        # Deliberately outside an `except`/`pytest.raises` block. Raising the
        # failure inside one means the construct catches it and the test passes
        # on exactly the bug it is meant to catch.
        pytest.fail(f"{label}: returned {result!r} instead of raising, so "
                    f"_shared_mcp_names would treat it as a real answer")

    # And the public wrapper degrades to the known core servers, never crashes.
    assert "mcp-debugger" in uninstall._shared_mcp_names()


def test_installers_hardcode_no_machine_specific_path():
    """A shipped installer must not carry this machine's directories."""
    for rel in ("scripts/setup.py", "clean-rag/install.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for pattern in (r"[A-Za-z]:[\\/]Users[\\/]", r"/home/[a-z]", r"/Users/[a-z]"):
            found = re.findall(pattern + r"\S*", text)
            assert not found, f"{rel} hardcodes a user-specific path: {found}"


# --- The safety guidance has to ship, not just exist on one machine ---------
#
# Both of these become ~/.claude/CLAUDE.md, which is why the section lives in
# both. install.bat and install.sh delete the destination and link the repo
# root copy; clean-rag/install.py's install_user_assets copies the portable one
# over the same path, and neither installer detects the other. Guidance in only
# one of them ships on only one of the two routes, and install.bat's `del` then
# `mklink` actively destroys a section that exists nowhere but the user's own
# file. That is what happened: the section was written straight into
# ~/.claude/CLAUDE.md, which is untracked, so no install path carried it.
INSTALLED_CLAUDE_MDS = ("CLAUDE.md", "clean-rag/portable/CLAUDE.md")

MCP_SAFETY_HEADING = "## MCP servers, and using them safely"


def _mcp_safety_section(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    assert MCP_SAFETY_HEADING in text, (
        f"{rel} has no {MCP_SAFETY_HEADING!r} section. This file is installed as "
        f"~/.claude/CLAUDE.md, so losing the section here means a machine that "
        f"installs by that route gets no MCP credential or safety guidance.")
    body = text.split(MCP_SAFETY_HEADING, 1)[1]
    return body.split("\n## ", 1)[0]


@pytest.mark.parametrize("rel", INSTALLED_CLAUDE_MDS)
def test_mcp_safety_section_ships_in_every_installed_claude_md(rel):
    assert _mcp_safety_section(rel).strip(), f"{rel}: section heading present but empty"


@pytest.mark.parametrize("rel", INSTALLED_CLAUDE_MDS)
def test_shipped_docs_say_where_credentials_belong(rel):
    """Naming the wrong location is how this broke the first time."""
    section = _mcp_safety_section(rel)
    for required in ("GITHUB_MCP_TOKEN", "settings.json", "${VAR}"):
        assert required in section, f"{rel}: section never mentions {required}"
    assert re.search(r"[Nn]ot\s+`?clean-rag/\.env", section), (
        f"{rel}: section does not warn that clean-rag/.env cannot carry these. "
        f"Claude Code never reads that file, so a token set there is invisible.")


def test_mcp_safety_section_does_not_drift_between_copies():
    """Two copies drift. This is what notices, same as test_installer_tables_agree."""
    first, second = (_mcp_safety_section(r) for r in INSTALLED_CLAUDE_MDS)
    assert first == second, (
        f"the MCP safety section differs between {INSTALLED_CLAUDE_MDS[0]} and "
        f"{INSTALLED_CLAUDE_MDS[1]}")


def test_env_example_cross_reference_resolves():
    """.env.example points at a section; that section must actually exist here."""
    text = (ROOT / "clean-rag/.env.example").read_text(encoding="utf-8")
    # Unwrap the comment: the reference spans two lines, each behind a "# ".
    flat = " ".join(line.lstrip("#").strip() for line in text.splitlines())
    referenced = re.search(r'"([^"]+)" section of CLAUDE\.md', flat)
    assert referenced, "clean-rag/.env.example no longer names a CLAUDE.md section"
    heading = "## " + referenced.group(1)
    for rel in INSTALLED_CLAUDE_MDS:
        assert heading in (ROOT / rel).read_text(encoding="utf-8"), (
            f".env.example points at {heading!r}, which {rel} does not contain")


def test_dotenv_example_does_not_promise_mcp_credentials_work_there():
    """clean-rag/.env is read by clean-rag's server, never by Claude Code.

    Documenting an MCP credential there sends the user to a file that cannot
    reach the server that needs it, and the failure is silent: the literal
    ${VAR} goes out as the bearer token.
    """
    text = (ROOT / "clean-rag/.env.example").read_text(encoding="utf-8")
    for var in ("GITHUB_MCP_TOKEN", "JUPYTER_TOKEN"):
        assert not re.search(rf"^#?\s*{var}=", text, re.MULTILINE), (
            f"{var} is presented as a settable key in .env.example, but "
            f"Claude Code never reads that file")
