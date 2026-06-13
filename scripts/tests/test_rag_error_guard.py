"""
Tests for scripts/rag-error-guard.py (PostToolUse hook on mcp__rag-server__* tools).

Exit codes:
  0 = no error detected
  2 = RAG server error detected — hard block
"""
from __future__ import annotations

import json
import pytest

from helpers import run_hook, posttooluse


def _rag_response(text: str) -> dict:
    return posttooluse("mcp__rag-server__rag_search", {}, tool_response=text)


def _rag_context_response(text: str) -> dict:
    return posttooluse("mcp__rag-server__rag_context", {}, tool_response=text)


class TestAllow:
    def test_allows_valid_search_response(self):
        response = json.dumps({
            "results": [{"content": "some text", "source": "file.py"}],
            "total_found": 1,
        })
        result = run_hook("rag-error-guard.py", _rag_response(response))
        assert result.returncode == 0

    def test_allows_valid_context_response(self):
        response = json.dumps({
            "agent_definition": "<agent>...",
            "relevant_knowledge": [],
            "sources_used": 3,
            "tier_summary": {},
        })
        result = run_hook("rag-error-guard.py", _rag_context_response(response))
        assert result.returncode == 0

    def test_allows_empty_results(self):
        response = json.dumps({"results": [], "total_found": 0})
        result = run_hook("rag-error-guard.py", _rag_response(response))
        assert result.returncode == 0

    def test_allows_index_response(self):
        response = json.dumps({
            "files_indexed": 42,
            "chunks_created": 200,
            "files_failed": 0,
        })
        result = run_hook("rag-error-guard.py", posttooluse("mcp__rag-server__rag_index", {}, tool_response=response))
        assert result.returncode == 0

    def test_allows_empty_input(self):
        result = run_hook("rag-error-guard.py", {})
        assert result.returncode == 0

    def test_allows_status_response(self):
        response = json.dumps({"collections": {}, "status": "ready"})
        result = run_hook("rag-error-guard.py", posttooluse("mcp__rag-server__rag_status", {}, tool_response=response))
        assert result.returncode == 0


class TestBlock:
    def test_blocks_connection_error(self):
        result = run_hook("rag-error-guard.py", _rag_response("connection refused: could not connect to server"))
        assert result.returncode == 2
        assert b"Do NOT fall back" in result.stderr or b"error" in result.stderr.lower()

    def test_blocks_traceback_response(self):
        result = run_hook("rag-error-guard.py", _rag_response("Traceback (most recent call last):\n  File server.py\nException: something failed"))
        assert result.returncode == 2

    def test_blocks_timeout_response(self):
        result = run_hook("rag-error-guard.py", _rag_response("timeout waiting for response from server"))
        assert result.returncode == 2

    def test_blocks_mcp_error_response(self):
        result = run_hook("rag-error-guard.py", _rag_response("mcp error: tool execution failed"))
        assert result.returncode == 2

    def test_blocks_internal_server_error(self):
        result = run_hook("rag-error-guard.py", _rag_response("internal server error occurred"))
        assert result.returncode == 2

    def test_blocks_total_index_research_failure(self):
        response = json.dumps({
            "sources_indexed": 0,
            "sources_failed": 3,
            "collection_path": "/some/path",
        })
        result = run_hook("rag-error-guard.py", posttooluse("mcp__rag-server__rag_index_research", {}, tool_response=response))
        assert result.returncode == 2
        assert b"0 sources" in result.stderr or b"failed" in result.stderr.lower()

    def test_blocks_embedded_research_index_not_found(self):
        response = json.dumps({
            "results": [],
            "total_found": 0,
            "error": "research index not found — run rag_index_research first",
        })
        result = run_hook("rag-error-guard.py", _rag_response(response))
        assert result.returncode == 2

    def test_blocks_embedded_project_not_indexed(self):
        response = json.dumps({
            "results": [],
            "total_found": 0,
            "error": "project not indexed — call rag_index_project first",
        })
        result = run_hook("rag-error-guard.py", _rag_response(response))
        assert result.returncode == 2


class TestPartialFailureAllowed:
    def test_partial_research_index_is_allowed(self):
        """Some succeeded + some failed = warn only, not block."""
        response = json.dumps({
            "sources_indexed": 2,
            "sources_failed": 1,
            "collection_path": "/some/path",
        })
        result = run_hook("rag-error-guard.py", posttooluse("mcp__rag-server__rag_index_research", {}, tool_response=response))
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# extract_text() edge cases (lines 77-79, 83)
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_list_payload_with_text_block(self):
        """tool_response is a list with a text block — hits lines 77-79."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__rag-server__rag_search",
            "tool_input": {},
            "tool_response": [{"type": "text", "text": "connection refused to RAG server"}],
        }
        result = run_hook("rag-error-guard.py", payload)
        assert result.returncode == 2

    def test_list_payload_non_text_blocks_returns_empty(self):
        """List with no text-type blocks → extract_text returns '' → allowed."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__rag-server__rag_search",
            "tool_input": {},
            "tool_response": [{"type": "image", "data": "base64data"}],
        }
        result = run_hook("rag-error-guard.py", payload)
        assert result.returncode == 0

    def test_dict_payload_dumps_to_json(self):
        """tool_response is a dict — hits line 83 (json.dumps)."""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__rag-server__rag_search",
            "tool_input": {},
            "tool_response": {"files_indexed": 10, "chunks_created": 50},
        }
        result = run_hook("rag-error-guard.py", payload)
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# check_total_index_failure() edge case (line 111)
# ---------------------------------------------------------------------------

class TestCheckTotalIndexFailureEdge:
    def test_indexed_zero_but_failed_also_zero_returns_none(self):
        """sources_indexed=0 but sources_failed=0 — line 111 return None, passes."""
        response = json.dumps({
            "sources_indexed": 0,
            "sources_failed": 0,
            "collection_path": "/some/path",
        })
        result = run_hook(
            "rag-error-guard.py",
            posttooluse("mcp__rag-server__rag_index_research", {}, tool_response=response),
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# main() edge paths (lines 118-119, 142-143, 170)
# ---------------------------------------------------------------------------

class TestMainEdgePaths:
    def test_invalid_json_stdin_returns_0(self):
        """Invalid JSON on stdin hits except branch (lines 118-119), returns 0."""
        import subprocess as _sp
        import sys as _sys
        from helpers import SCRIPTS_DIR as _SD
        result = _sp.run(
            [_sys.executable, str(_SD / "rag-error-guard.py")],
            input=b"INVALID JSON INPUT",
            capture_output=True,
        )
        assert result.returncode == 0

    def test_success_signal_in_unparseable_text_passes(self):
        """text has a success signal but is not valid JSON (lines 142-143)."""
        raw_text = '"results" present but text is not parseable json {{{'
        result = run_hook("rag-error-guard.py", _rag_response(raw_text))
        assert result.returncode == 0

    def test_ambiguous_text_returns_0(self):
        """No success signals, no error signals — ambiguous → line 170 return 0."""
        result = run_hook("rag-error-guard.py", _rag_response("processing complete"))
        assert result.returncode == 0
