"""mcp.grep.app is the code search path that works for everybody with no setup.

No account, no API key, no per machine configuration. That is the point: a fresh
ClaudeBoost clone can answer "does this already exist" on the day it is installed,
and nothing about the path is tied to one user's credentials.

It replaced the scraped grep.app/api/search endpoint as the default keyless path
because that one answers HTTP 429 on a first request from a fresh IP and has no
key to raise the limit. The scrape is kept as a second fallback, not deleted.

Every network call here is faked. A test that hit the real endpoint would be a
liveness check for someone else's service, would fail offline, and would say
nothing about whether this code parses the response correctly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import github_search as gs  # noqa: E402


# A real block, trimmed. Shape taken from an actual mcp.grep.app response.
_BLOCK = """Repository: anthropics/claude-code
Path: plugins/security-guidance/hooks/security_reminder_hook.py
URL: https://github.com/anthropics/claude-code/blob/main/plugins/x.py
License: Apache-2.0

Snippets:
--- Snippet 1 (Line 39) ---

MAX_DIFF_FILES = int(os.environ.get("MAX_DIFF_FILES", "30"))

--- Snippet 2 (Line 82) ---

if payload.get("stop_hook_active"):
    sys.exit(0)
"""


def _rpc_result(blocks, is_error=False):
    result = {"content": [{"type": "text", "text": b} for b in blocks]}
    if is_error:
        result["isError"] = True
    return {"jsonrpc": "2.0", "id": 1, "result": result}


class FakeResponse:
    def __init__(self, status_code=200, body="", json_data=None, headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = json.dumps(json_data) if json_data is not None else body
        self.headers = headers or {}

    def json(self):
        """The MCP path reads .text; the scraped path calls .json(). One fake
        has to serve both or the fallback-chain test fails on the fake."""
        if self._json is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json


class FakeClient:
    def __init__(self, responses, calls, **kwargs):
        self._responses = responses
        self._calls = calls
        self.timeout = kwargs.get("timeout")
        self.headers = kwargs.get("headers")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _serve(self, url, **extra):
        self._calls.append({"url": url, "timeout": self.timeout,
                            "headers": self.headers, **extra})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, json=None):
        return self._serve(url, body=json)

    # The scraped grep.app path is a GET. Without this the fallback-chain test
    # fails on the fake rather than on the code it is meant to exercise.
    def get(self, url, params=None):
        return self._serve(url, params=params)


@pytest.fixture()
def http(monkeypatch):
    state = {"responses": [], "calls": []}
    monkeypatch.setattr(gs, "_BACKOFF_S", (0.0, 0.0))
    monkeypatch.setattr(
        gs.httpx, "Client",
        lambda **kw: FakeClient(state["responses"], state["calls"], **kw),
    )
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return state


# ── the request it sends ─────────────────────────────────────────────────────

class TestTheRequest:
    def test_it_calls_the_documented_tool_over_json_rpc(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        gs.grep_mcp_code_search("stop_hook_active")
        call = http["calls"][0]
        assert call["url"] == gs.GREP_MCP_URL
        assert call["body"]["jsonrpc"] == "2.0"
        assert call["body"]["method"] == "tools/call"
        assert call["body"]["params"]["name"] == "searchGitHub"
        assert call["body"]["params"]["arguments"]["query"] == "stop_hook_active"

    def test_it_sends_no_authorization_header(self, http):
        """The whole reason this path exists. An Authorization header would mean
        it is not the keyless path, whatever the docstring claims."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        gs.grep_mcp_code_search("q")
        headers = http["calls"][0]["headers"] or {}
        assert not any(k.lower() == "authorization" for k in headers)

    def test_it_accepts_both_body_types(self, http):
        """Streamable HTTP may answer as JSON or as SSE. Advertising only one
        invites the server to pick the other."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        gs.grep_mcp_code_search("q")
        accept = (http["calls"][0]["headers"] or {}).get("Accept", "")
        assert "application/json" in accept
        assert "text/event-stream" in accept

    def test_language_is_sent_as_a_list(self, http):
        """The tool takes a list. A bare string is silently dropped, which reads
        as "no results for this language" rather than "the filter never applied"."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        gs.grep_mcp_code_search("q", language="Python")
        assert http["calls"][0]["body"]["params"]["arguments"]["language"] == ["Python"]

    def test_language_is_omitted_when_not_given(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        gs.grep_mcp_code_search("q")
        assert "language" not in http["calls"][0]["body"]["params"]["arguments"]

    @pytest.mark.parametrize("bad", ["", "   ", None, 42])
    def test_an_empty_query_never_reaches_the_network(self, http, bad):
        out = gs.grep_mcp_code_search(bad)
        assert out["error"] == "Invalid query"
        assert http["calls"] == []


# ── parsing the response ─────────────────────────────────────────────────────

class TestParsing:
    def test_it_extracts_repo_path_and_url(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        hit = gs.grep_mcp_code_search("q")["results"][0]
        assert hit["repo"] == "anthropics/claude-code"
        assert hit["path"] == "plugins/security-guidance/hooks/security_reminder_hook.py"
        assert hit["url"].startswith("https://github.com/")

    def test_snippets_are_code_not_the_license_header(self, http):
        """The header block sits between the URL and the first snippet marker.
        Keeping it handed the caller 'License: Apache-2.0' as if it were a match,
        which is worse than returning nothing: it looks like a real reference."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        matches = gs.grep_mcp_code_search("q")["results"][0]["matches"]
        assert len(matches) == 2
        joined = "\n".join(matches)
        assert "License:" not in joined
        assert "Snippets:" not in joined
        assert "MAX_DIFF_FILES" in matches[0]
        assert "stop_hook_active" in matches[1]

    def test_a_block_with_no_snippets_yields_no_matches_not_a_crash(self, http):
        block = "Repository: o/r\nPath: a.py\nURL: https://github.com/o/r/blob/main/a.py\nLicense: MIT\n"
        http["responses"] = [FakeResponse(json_data=_rpc_result([block]))]
        hit = gs.grep_mcp_code_search("q")["results"][0]
        assert hit["matches"] == []
        assert hit["repo"] == "o/r"

    def test_an_unrecognisable_block_is_skipped_not_guessed_at(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result(["total noise", _BLOCK]))]
        out = gs.grep_mcp_code_search("q")
        assert len(out["results"]) == 1
        assert out["results"][0]["repo"] == "anthropics/claude-code"

    def test_stars_is_zero_because_grep_app_does_not_report_it(self, http):
        """Zero means unknown here. Inventing a number would make a caller rank
        results on a value nothing measured."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        assert gs.grep_mcp_code_search("q")["results"][0]["stars"] == 0

    def test_max_results_is_honoured(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK] * 5))]
        out = gs.grep_mcp_code_search("q", max_results=2)
        assert len(out["results"]) == 2
        assert out["total_count"] == 5, "total must report what the server found"

    def test_an_sse_body_parses_the_same_as_json(self, http):
        payload = json.dumps(_rpc_result([_BLOCK]))
        http["responses"] = [FakeResponse(body=f"event: message\ndata: {payload}\n\n")]
        out = gs.grep_mcp_code_search("q")
        assert out["error"] is None
        assert out["results"][0]["repo"] == "anthropics/claude-code"

    def test_zero_results_is_an_answer_not_an_error(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result([]))]
        out = gs.grep_mcp_code_search("nothing matches this")
        assert out["results"] == []
        assert out["error"] is None
        assert not out.get("needs_user_action")


# ── failures ─────────────────────────────────────────────────────────────────

class TestFailures:
    def test_a_json_rpc_error_is_reported_not_read_as_zero_hits(self, http):
        http["responses"] = [FakeResponse(json_data={
            "jsonrpc": "2.0", "id": 1,
            "error": {"code": -32601, "message": "Method not found"}})]
        out = gs.grep_mcp_code_search("q")
        assert out["results"] == []
        assert "Method not found" in out["error"]

    def test_a_tool_level_iserror_is_reported(self, http):
        """A tool failure arrives as isError with the reason in the text, not as
        a JSON-RPC error. Unchecked, it is indistinguishable from 0 hits."""
        http["responses"] = [FakeResponse(json_data=_rpc_result(["rate limited"], is_error=True))]
        out = gs.grep_mcp_code_search("q")
        assert out["results"] == []
        assert "rate limited" in out["error"]

    def test_an_unparseable_body_says_so_and_shows_it(self, http):
        http["responses"] = [FakeResponse(body="<html>502 bad gateway</html>")]
        out = gs.grep_mcp_code_search("q")
        assert out["results"] == []
        assert "unparseable" in out["error"]
        assert "502" in out["error"]

    def test_a_transient_5xx_is_retried_then_succeeds(self, http):
        http["responses"] = [FakeResponse(status_code=503),
                             FakeResponse(json_data=_rpc_result([_BLOCK]))]
        out = gs.grep_mcp_code_search("q")
        assert out["error"] is None
        assert len(http["calls"]) == 2

    def test_a_4xx_is_answered_not_retried(self, http):
        http["responses"] = [FakeResponse(status_code=404)]
        out = gs.grep_mcp_code_search("q")
        assert "404" in out["error"]
        assert len(http["calls"]) == 1

    def test_it_gives_up_after_max_attempts(self, http):
        http["responses"] = [gs.httpx.ConnectError("no route")
                             for _ in range(gs._MAX_ATTEMPTS)]
        out = gs.grep_mcp_code_search("q")
        assert f"{gs._MAX_ATTEMPTS} attempts" in out["error"]


# ── the fallback chain ───────────────────────────────────────────────────────

class TestFallbackOrder:
    def test_no_token_tries_the_mcp_endpoint_first(self, http):
        """Ordering is the whole fix. The scrape returns 429 on a first request
        from a fresh IP, so trying it first means most users see a failure."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        out = gs.github_code_search("q")
        assert out["source"] == "mcp.grep.app"
        assert http["calls"][0]["url"] == gs.GREP_MCP_URL

    def test_it_never_spends_a_request_that_must_401(self, http):
        http["responses"] = [FakeResponse(json_data=_rpc_result([_BLOCK]))]
        gs.github_code_search("q")
        assert gs.GITHUB_CODE_SEARCH_URL not in [c["url"] for c in http["calls"]]

    def test_both_keyless_paths_down_escalates_with_both_reasons(self, http, monkeypatch):
        monkeypatch.setattr(gs, "grep_mcp_code_search", lambda *a, **k: {
            "results": [], "total_count": 0, "source": "mcp.grep.app",
            "error": "mcp is down"})
        monkeypatch.setattr(gs, "grep_app_code_search", lambda *a, **k: {
            "results": [], "total_count": 0, "source": "grep.app",
            "error": "scrape is 429"})
        out = gs.github_code_search("q")
        assert out["needs_user_action"] is True
        assert "mcp is down" in out["error"]
        assert "scrape is 429" in out["error"], "both failures must be named, not just the last"
        assert "GITHUB_TOKEN" in out["error"]

    def test_a_working_search_with_zero_hits_does_not_escalate(self, http):
        """The distinction that makes escalation worth reading: a search that ran
        and found nothing is an answer, not a blocked task."""
        http["responses"] = [FakeResponse(json_data=_rpc_result([]))]
        out = gs.github_code_search("nothing matches this")
        assert out["results"] == []
        assert not out.get("needs_user_action")

    def test_the_scrape_is_still_reachable_as_a_second_fallback(self, http, monkeypatch):
        monkeypatch.setattr(gs, "grep_mcp_code_search", lambda *a, **k: {
            "results": [], "total_count": 0, "source": "mcp.grep.app",
            "error": "mcp is down"})
        http["responses"] = [FakeResponse(json_data={
            "facets": {"count": 1},
            "hits": {"hits": [{"repo": {"raw": "o/r"}, "path": {"raw": "a.py"},
                               "content": {"snippet": "<pre>code here</pre>"}}]}})]
        out = gs.github_code_search("q")
        assert out["source"] == "grep.app"
        assert out["results"][0]["repo"] == "o/r"


class TestPortability:
    def test_nothing_in_this_path_needs_a_credential(self):
        """The requirement in one assertion: a fresh clone on any machine, with
        no env var, no key file and no signup, still gets code search."""
        import inspect
        src = inspect.getsource(gs.grep_mcp_code_search)
        assert "GITHUB_TOKEN" not in src
        assert "Authorization" not in src
        assert "os.environ" not in src
