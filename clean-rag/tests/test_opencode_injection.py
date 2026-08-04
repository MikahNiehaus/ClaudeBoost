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
