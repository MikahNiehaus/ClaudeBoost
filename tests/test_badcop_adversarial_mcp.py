"""Adversarial checks written by bad-cop against the MCP-registration diff.

These are NOT assertions of current (possibly buggy) behavior picked after the
fact — each test encodes an invariant stated in the task's correctness
properties / attack list, derived before looking at whether the code passes:

  - INV1: a server's reported connection status must be derived from ITS OWN
    line in `claude mcp list`, never from the presence of the word
    "Connected" anywhere else in the full multi-line output.
  - INV2: the substring check used to decide "mdb is already registered" must
    not be satisfied by an unrelated server whose name merely contains "mdb"
    as a substring (e.g. a real-world "cmdb" MCP server).

Both are run against the real, unmodified scripts/setup.py and
scripts/boost-run.py modules (imported, not re-implemented), so a pass here
is real execution evidence, not a description.
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(rel.replace("/", "_").replace(".", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_connected_status_leaks_across_servers_in_register_one():
    """INV1. mcp-debugger is Connected; playwright is registered but failed.

    A correct implementation reports playwright as NOT connected. The actual
    implementation reports it as connected, because `_register_one` tests
    "Connected" in listed (the WHOLE multi-line `claude mcp list` output)
    instead of in the matched line for that server.
    """
    setup_mod = _load("scripts/setup.py")

    listed = (
        "mcp-debugger: npx -y @debugmcp/mcp-debugger stdio - \u2713 Connected\n"
        "playwright: npx -y @playwright/mcp@latest - \u2717 Failed to connect"
    )

    messages = []
    setup_mod._ok = lambda m: messages.append(("OK", m))
    setup_mod._warn = lambda m: messages.append(("WARN", m))
    setup_mod._info = lambda m: messages.append(("INFO", m))
    setup_mod._skip = lambda m: messages.append(("SKIP", m))
    setup_mod.shutil.which = lambda name: "C:/fake/" + name  # 'npx' is "present"

    playwright_server = next(s for s in setup_mod.MCP_SERVERS if s["name"] == "playwright")
    setup_mod._register_one(["claude"], listed, playwright_server)

    print("Captured messages:", messages)

    reported_connected = any(
        level == "OK" and "already registered and connected" in msg
        for level, msg in messages
    )
    reported_not_connected = any(
        level == "WARN" and "not connected" in msg
        for level, msg in messages
    )

    assert not reported_connected, (
        "BUG CONFIRMED: playwright was reported as 'already registered and "
        "connected' solely because mcp-debugger's line elsewhere in the same "
        "`claude mcp list` output contained the word Connected. "
        f"messages={messages}"
    )
    assert reported_not_connected, f"expected a not-connected warning, got: {messages}"


def test_mdb_substring_collision_with_unrelated_cmdb_server():
    """INV2. An unrelated 'cmdb' MCP server is registered and connected.

    register_mcp_servers() must still attempt to register the real mdb
    (MDB-MCP) server, because mdb itself was never actually registered.
    The actual implementation's `if "mdb" in listed:` check is satisfied by
    the substring inside "cmdb", so it silently believes mdb is already
    registered and skips it — the native debugger never gets installed and
    no warning is ever surfaced.
    """
    setup_mod = _load("scripts/setup.py")

    listed = (
        "mcp-debugger: npx -y @debugmcp/mcp-debugger stdio - \u2713 Connected\n"
        "playwright: npx -y @playwright/mcp@latest - \u2713 Connected\n"
        "test-coverage: npx -y test-coverage-mcp - \u2713 Connected\n"
        "chrome-devtools: npx -y chrome-devtools-mcp@latest - \u2713 Connected\n"
        "cmdb: npx -y cmdb-mcp-server - \u2713 Connected"
    )

    messages = []
    setup_mod._ok = lambda m: messages.append(("OK", m))
    setup_mod._warn = lambda m: messages.append(("WARN", m))
    setup_mod._info = lambda m: messages.append(("INFO", m))
    setup_mod._skip = lambda m: messages.append(("SKIP", m))

    setup_mod._claude_cmd = lambda: ["claude"]
    setup_mod.run_cmd = lambda args: (0, listed)
    setup_mod.shutil.which = lambda name: "C:/fake/" + name

    mdb_clone_called = []
    setup_mod._mdb_mcp_server = lambda: (mdb_clone_called.append(True), None)[1]

    setup_mod.register_mcp_servers()

    print("Captured messages:", messages)
    print("mdb clone attempted:", bool(mdb_clone_called))

    claimed_already_registered = any(
        "MDB-MCP already registered" in msg for _, msg in messages
    )

    assert not claimed_already_registered or mdb_clone_called, (
        "BUG CONFIRMED: register_mcp_servers() believed MDB-MCP was already "
        "registered because the unrelated server name 'cmdb' contains the "
        "substring 'mdb', and it never even attempted to clone/register the "
        f"real mdb server. messages={messages}"
    )


def test_boost_run_mdb_substring_collision_with_cmdb():
    """Same INV2 collision, but in boost-run.py's health-check reporting.

    step_mcp_debugger prints "mdb: registered (native GDB/LLDB, optional)"
    based on `any("mdb" in l.lower() for l in lines)`, which is also
    satisfied by an unrelated "cmdb" server line.
    """
    boost_run = _load("scripts/boost-run.py")

    fake_output = (
        "mcp-debugger: npx -y @debugmcp/mcp-debugger stdio - \u2713 Connected\n"
        "playwright: npx -y @playwright/mcp@latest - \u2713 Connected\n"
        "test-coverage: npx -y test-coverage-mcp - \u2713 Connected\n"
        "chrome-devtools: npx -y chrome-devtools-mcp@latest - \u2713 Connected\n"
        "cmdb: npx -y cmdb-mcp-server - \u2713 Connected"
    )

    boost_run._run = lambda args, timeout=20: (0, fake_output)

    printed = []
    import builtins
    real_print = builtins.print
    try:
        builtins.print = lambda *a, **kw: printed.append(" ".join(str(x) for x in a))
        boost_run.step_mcp_debugger()
    finally:
        builtins.print = real_print

    print("Printed lines:", printed)

    falsely_claims_mdb = any("mdb: registered" in line for line in printed)
    assert not falsely_claims_mdb, (
        "BUG CONFIRMED: step_mcp_debugger reports mdb as registered solely "
        f"because of the unrelated 'cmdb' server name. printed={printed}"
    )
