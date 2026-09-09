#!/usr/bin/env python3
"""Tests for the OpenCode MCP server's tool surface.

Rewritten from a manual demo script. The previous version passed
unconditionally and tested nothing:

  * ``test_mcp_call`` was a HELPER taking two required arguments, but its name
    made pytest collect it as a test, so it errored on a missing ``tool_name``
    fixture on every run.
  * It spawned ``/c/prj/ClaudeBoost/clean-rag/mcp/opencode_mcp_server.py``, a
    path from a different machine that does not exist here, so every call hit
    ``FileNotFoundError``, was swallowed into ``{"error": ...}``, and the test
    body returned ``False``/``None``.
  * The bodies ``return`` a bool instead of asserting, and pytest treats any
    non-None return as a pass, so a total failure still reported green.

These exercise the request handler in process rather than over a subprocess.
That is the part with the logic in it, and it needs no server, no network and
no hardcoded machine paths.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).resolve().parent.parent / "mcp" / "opencode_mcp_server.py"


def _load_server_module():
    spec = importlib.util.spec_from_file_location("opencode_mcp_server", _SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["opencode_mcp_server"] = module
    spec.loader.exec_module(module)
    return module


def _tools_of(server):
    """The tool declarations, however this server chooses to expose them.

    Some versions have a `tools` list attribute, others a get_tools()/tools()
    method. Resolving it here keeps the assertions about tool CONTENT from
    breaking on a refactor of the accessor.
    """
    for name in ("get_tools", "tools", "list_tools", "_tools"):
        if not hasattr(server, name):
            continue
        attr = getattr(server, name)
        return attr() if callable(attr) else attr
    pytest.skip("server exposes no recognisable tool declaration list")


@pytest.fixture(scope="module")
def server():
    if not _SERVER_PATH.exists():
        pytest.skip(f"OpenCode MCP server not present at {_SERVER_PATH}")
    module = _load_server_module()
    cls = next(
        (getattr(module, n) for n in dir(module)
         if n.endswith("Server") and isinstance(getattr(module, n), type)),
        None,
    )
    if cls is None:
        pytest.skip("no Server class found in opencode_mcp_server")
    return cls()


def test_server_file_exists_at_the_path_the_tests_use():
    """The old suite pointed at a nonexistent path and still passed."""
    assert _SERVER_PATH.exists(), (
        f"{_SERVER_PATH} is missing; the previous suite hardcoded "
        f"/c/prj/ClaudeBoost/... and silently passed against it"
    )


def test_rag_search_without_a_project_path_reports_an_error(server):
    """No project path means nothing to search, and it must SAY so.

    Returning an empty list here would be indistinguishable from "searched and
    found nothing", which is the misreading the whole provenance/staleness
    effort exists to prevent.
    """
    result = server.rag_search("collision detection", project_path=None)
    assert result.get("results") == []
    assert result.get("error"), "an unsearchable request must carry a reason"
    assert "project_path" in result["error"]


def test_inject_full_context_infers_a_project_path_from_the_filepath(server, tmp_path):
    """The regression this file failed to catch.

    inject_full_context used to call rag_search(prompt) with no project_path,
    so it always hit the error branch above and never searched any index. It
    then read the empty result as "nothing found" and went straight to the web.
    """
    repo = tmp_path / "someproject"
    (repo / ".git").mkdir(parents=True)
    target = repo / "src" / "thing.py"
    target.parent.mkdir(parents=True)
    target.write_text("def thing():\n    return 1\n", encoding="utf-8")

    inferred = server._infer_project_path(str(target))
    assert inferred is not None, "a file inside a git repo must resolve to a project"
    assert Path(inferred) == repo


def test_infer_project_path_prefers_the_deepest_registered_project(server, tmp_path, monkeypatch):
    """A repo nested inside another must resolve to the inner, more specific one."""
    outer = tmp_path / "outer"
    inner = outer / "nested"
    (outer / ".git").mkdir(parents=True)
    (inner / ".git").mkdir(parents=True)
    f = inner / "a.py"
    f.write_text("x = 1\n", encoding="utf-8")

    assert Path(server._infer_project_path(str(f))) == inner


def test_infer_project_path_returns_none_without_a_filepath(server):
    assert server._infer_project_path(None) is None
    assert server._infer_project_path("") is None


def test_inject_full_context_is_declared_with_project_path(server):
    """The tool schema must expose what the implementation now accepts."""
    tools = _tools_of(server)
    inject = next(t for t in tools if t["name"] == "inject_full_context")
    props = inject["inputSchema"]["properties"]
    assert "project_path" in props, (
        "inject_full_context accepts project_path but never advertises it, so "
        "no MCP client would ever send one"
    )


def test_unknown_tool_is_rejected(server):
    result = server.handle_tool_call("no_such_tool", {})
    assert "error" in result
    assert "no_such_tool" in result["error"]


def test_every_declared_tool_has_a_schema(server):
    tools = _tools_of(server)
    assert tools, "the server declares no tools at all"
    for tool in tools:
        assert tool.get("name"), f"unnamed tool: {tool}"
        assert tool.get("description"), f"{tool['name']} has no description"
        schema = tool.get("inputSchema")
        assert isinstance(schema, dict), f"{tool['name']} has no inputSchema"
        assert schema.get("type") == "object"
        assert isinstance(schema.get("properties"), dict)
        # Anything listed as required must actually be declared.
        for req in schema.get("required", []):
            assert req in schema["properties"], (
                f"{tool['name']} requires {req!r} but does not declare it"
            )


def test_tool_declarations_are_json_serialisable(server):
    """MCP sends these over stdio; a non serialisable schema breaks the handshake."""
    tools = _tools_of(server)
    json.dumps(tools)


# ---------------------------------------------------------------------------
# Surviving bad input, and the tools actually working
#
# Unlike a Claude Code hook, which is one process per tool call, this server is
# one process for a whole OpenCode session. A single unhandled line does not
# fail one request, it kills every request the session would ever make. So the
# stdio loop is driven as a real subprocess here: in process tests cannot see
# whether the loop kept going.
# ---------------------------------------------------------------------------

import os          # noqa: E402
import subprocess  # noqa: E402

_CLEAN_RAG = _SERVER_PATH.parents[1]

# Valid JSON that is not a JSON-RPC object. json.loads accepts every one of
# these, so `request.get("id")` was reached with a str, a list or None.
_NOT_AN_OBJECT = [
    "null",
    "true",
    "123",
    '"hello"',
    "[]",
    '[{"jsonrpc": "2.0", "id": 9, "method": "tools/list"}]',
]


def _declared_env(scratch: Path) -> dict:
    """Everything the server needs, named rather than inherited.

    APPDATA is in the list because user site-packages lives under it on
    Windows: drop it and radon disappears, which quietly turns a full
    code_metrics result into a partial one.
    """
    keep = ("PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
            "APPDATA", "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["TEMP"] = env["TMP"] = str(scratch)
    env["CLEAN_RAG_HOME"] = str(_CLEAN_RAG)
    env["METRICS_CACHE_DIR"] = str(scratch / "metrics-cache")
    return env


def _drive(lines: list[str], scratch: Path) -> subprocess.CompletedProcess:
    # encoding and errors named explicitly. text=True alone decodes with
    # locale.getpreferredencoding(), cp1252 on this machine, and the server
    # logs file paths: one character outside cp1252 kills the reader thread,
    # subprocess.run still returns, and .stdout comes back None so the caller
    # fails with AttributeError rather than an error it can act on.
    return subprocess.run(
        [sys.executable, str(_SERVER_PATH)],
        input="\n".join(lines) + "\n",
        capture_output=True, encoding="utf-8", errors="replace",
        env=_declared_env(scratch), timeout=300,
    )


def _responses(result: subprocess.CompletedProcess) -> list[dict]:
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


@pytest.mark.parametrize("bad_line", _NOT_AN_OBJECT)
def test_a_line_that_is_not_a_request_object_does_not_end_the_session(bad_line, tmp_path):
    result = _drive([bad_line, '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'], tmp_path)

    assert result.returncode == 0, (
        f"the server died on {bad_line!r}; every later tool call in the "
        f"OpenCode session fails until it is restarted:\n{result.stderr[-800:]}"
    )
    answers = _responses(result)
    listed = [r for r in answers if r.get("id") == 1]
    assert listed, (
        f"the well formed request after {bad_line!r} went unanswered; "
        f"got {answers}"
    )
    assert listed[0]["result"]["tools"], "tools/list came back empty"


def test_an_unparseable_line_does_not_end_the_session(tmp_path):
    result = _drive(["{not json", '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'], tmp_path)
    assert result.returncode == 0, result.stderr[-800:]
    codes = [r["error"]["code"] for r in _responses(result) if "error" in r]
    assert -32700 in codes, f"expected a parse error, got {codes}"


def test_code_metrics_returns_real_numbers_rather_than_an_error(tmp_path):
    """It used to POST to an HTTP /metrics route that the server does not serve.

    Every call came back 404, so a tool advertised in tools/list was permanently
    broken. Asserting on the numbers, not on the transport, so this keeps
    meaning the same thing if the call ever moves back behind a real route.
    """
    target = _CLEAN_RAG / "server" / "web_search.py"
    call = json.dumps({
        "jsonrpc": "2.0", "id": 7, "method": "tools/call",
        "params": {"name": "code_metrics", "arguments": {"filepath": str(target)}},
    })
    result = _drive([call], tmp_path)
    assert result.returncode == 0, result.stderr[-800:]

    answers = _responses(result)
    assert answers, f"no response at all: {result.stderr[-800:]}"
    payload = json.loads(answers[0]["result"]["content"][0]["text"])
    assert not payload.get("error"), payload
    assert payload["lines_of_code"] > 0, payload
    assert payload["call_graph"]["functions"], payload


def test_code_metrics_reports_a_missing_file_instead_of_inventing_numbers(tmp_path):
    call = json.dumps({
        "jsonrpc": "2.0", "id": 8, "method": "tools/call",
        "params": {"name": "code_metrics",
                   "arguments": {"filepath": str(tmp_path / "nope.py")}},
    })
    result = _drive([call], tmp_path)
    assert result.returncode == 0, result.stderr[-800:]
    payload = json.loads(_responses(result)[0]["result"]["content"][0]["text"])
    assert payload.get("error"), payload
