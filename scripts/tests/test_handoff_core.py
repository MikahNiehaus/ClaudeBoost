"""
Tests for scripts/handoff_core.py (library module).

Covers: extract_conversation, format_conversation_md, and helpers.
Tested by direct import — not via subprocess.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import handoff_core


# ---------------------------------------------------------------------------
# _is_file_path
# ---------------------------------------------------------------------------

class TestIsFilePath:
    def test_unix_absolute_path(self):
        assert handoff_core._is_file_path("/home/user/foo.py") is True

    def test_windows_backslash_path(self):
        assert handoff_core._is_file_path(r"C:\Users\foo\bar.py") is True

    def test_windows_forward_slash_path(self):
        assert handoff_core._is_file_path("C:/Users/foo/bar.py") is True

    def test_relative_path_rejected(self):
        assert handoff_core._is_file_path("relative/path.py") is False

    def test_short_string_rejected(self):
        assert handoff_core._is_file_path("ab") is False

    def test_non_string_rejected(self):
        assert handoff_core._is_file_path(123) is False

    def test_shell_injection_rejected(self):
        assert handoff_core._is_file_path("/tmp/foo && rm -rf /") is False

    def test_pipe_rejected(self):
        assert handoff_core._is_file_path("/foo/bar | cat") is False

    def test_semicolon_rejected(self):
        assert handoff_core._is_file_path("/foo; echo") is False

    def test_backtick_rejected(self):
        assert handoff_core._is_file_path("/foo`cmd`") is False

    def test_dollar_paren_rejected(self):
        assert handoff_core._is_file_path("/foo$(cmd)") is False

    def test_newline_rejected(self):
        assert handoff_core._is_file_path("/foo\nbar") is False


# ---------------------------------------------------------------------------
# _collect_paths
# ---------------------------------------------------------------------------

class TestCollectPaths:
    def test_finds_file_path_key(self):
        paths = set()
        handoff_core._collect_paths({"file_path": "/tmp/foo.py"}, paths)
        assert "/tmp/foo.py" in paths

    def test_finds_path_key(self):
        paths = set()
        handoff_core._collect_paths({"path": "/tmp/bar.py"}, paths)
        assert "/tmp/bar.py" in paths

    def test_ignores_non_path_key(self):
        paths = set()
        handoff_core._collect_paths({"description": "/not/collected"}, paths)
        assert len(paths) == 0

    def test_recurses_nested(self):
        paths = set()
        handoff_core._collect_paths({"tool_use": {"input": {"file_path": "/deep/path.py"}}}, paths)
        assert "/deep/path.py" in paths

    def test_recurses_list(self):
        paths = set()
        handoff_core._collect_paths([{"file_path": "/list/item.py"}], paths)
        assert "/list/item.py" in paths

    def test_ignores_unsafe_path(self):
        paths = set()
        handoff_core._collect_paths({"file_path": "/foo && rm -rf /"}, paths)
        assert len(paths) == 0


# ---------------------------------------------------------------------------
# _similarity and _dedup
# ---------------------------------------------------------------------------

class TestDedup:
    def test_removes_identical_messages(self):
        messages = ["hello world", "hello world", "something different"]
        result = handoff_core._dedup(messages)
        assert len(result) == 2
        assert "hello world" in result
        assert "something different" in result

    def test_keeps_distinct_messages(self):
        messages = ["aaa", "bbb", "ccc"]
        result = handoff_core._dedup(messages)
        assert len(result) == 3

    def test_empty_list(self):
        assert handoff_core._dedup([]) == []

    def test_single_item(self):
        assert handoff_core._dedup(["only one"]) == ["only one"]

    def test_similarity_truncates_at_200(self):
        # Two long strings that are nearly identical past char 200
        s1 = "x" * 200 + "different"
        s2 = "x" * 200 + "also different"
        # They look the same when truncated — should be deduped
        result = handoff_core._dedup([s1, s2], threshold=0.85)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# extract_conversation
# ---------------------------------------------------------------------------

class TestExtractConversation:
    def test_returns_none_for_missing_file(self, tmp_path):
        result = handoff_core.extract_conversation(str(tmp_path / "nonexistent.jsonl"))
        assert result is None

    def test_returns_none_for_empty_file(self, tmp_path):
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is None

    def test_returns_none_for_no_useful_content(self, tmp_path):
        f = tmp_path / "nouseful.jsonl"
        # Only junk entries
        entries = [
            json.dumps({"type": "user", "message": {"content": [{"type": "interrupt", "text": "[Request interrupted by user]"}]}}),
        ]
        f.write_text("\n".join(entries), encoding="utf-8")
        # No user messages and no file paths → None
        result = handoff_core.extract_conversation(str(f))
        assert result is None

    def test_extracts_user_message_string(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        entry = {"type": "user", "message": {"content": "Fix the login bug"}}
        f.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        assert "Fix the login bug" in result["user_messages"]

    def test_extracts_user_message_list(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        entry = {
            "type": "user",
            "message": {"content": [{"type": "text", "text": "Add unit tests"}]}
        }
        f.write_text(json.dumps(entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        assert "Add unit tests" in result["user_messages"]

    def test_skips_junk_user_messages(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        # The junk message is filtered out, but we need at least one real message or file path
        entries = [
            json.dumps({"type": "user", "message": {"content": "[Request interrupted by user]"}}),
            json.dumps({"type": "user", "message": {"content": "Real message here for the user"}}),
        ]
        f.write_text("\n".join(entries), encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        if result:
            assert "[Request interrupted by user]" not in result["user_messages"]

    def test_extracts_assistant_text_snippet(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        # Need a user message too so result isn't None
        user_entry = {"type": "user", "message": {"content": "please help"}}
        assistant_entry = {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Here is my analysis of the code"}]
            }
        }
        f.write_text(json.dumps(user_entry) + "\n" + json.dumps(assistant_entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        assert any("Here is my analysis" in s for s in result["assistant_snippets"])

    def test_skips_api_error_assistant_messages(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        user_entry = {"type": "user", "message": {"content": "real user message here"}}
        assistant_entry = {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "API Error: rate_limit exceeded"}]
            }
        }
        f.write_text(json.dumps(user_entry) + "\n" + json.dumps(assistant_entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        if result:
            assert not any("API Error" in s for s in result["assistant_snippets"])

    def test_extracts_file_paths_from_tool_use(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        assistant_entry = {
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "input": {"file_path": "/src/main.py"}
                }]
            }
        }
        user_entry = {"type": "user", "message": {"content": "show me the main file"}}
        f.write_text(json.dumps(user_entry) + "\n" + json.dumps(assistant_entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        assert "/src/main.py" in result["files_touched"]

    def test_skips_blank_lines(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        entry = {"type": "user", "message": {"content": "meaningful work item"}}
        content = "\n\n" + json.dumps(entry) + "\n\n"
        f.write_text(content, encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None

    def test_skips_malformed_json_lines(self, tmp_path):
        f = tmp_path / "transcript.jsonl"
        content = "NOT JSON\n" + json.dumps({"type": "user", "message": {"content": "real message text here"}}) + "\n"
        f.write_text(content, encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None

    def test_truncates_long_transcripts(self, tmp_path):
        f = tmp_path / "long.jsonl"
        # More than MAX_LINES (2000) entries
        entries = []
        for i in range(2100):
            entries.append(json.dumps({"type": "user", "message": {"content": f"message {i}"}}))
        f.write_text("\n".join(entries), encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None

    def test_respects_max_user_limit(self, tmp_path):
        f = tmp_path / "many.jsonl"
        entries = [json.dumps({"type": "user", "message": {"content": f"message number {i} with extra text"}}) for i in range(30)]
        f.write_text("\n".join(entries), encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        assert len(result["user_messages"]) <= 15  # max_user default

    def test_returns_sorted_files(self, tmp_path):
        f = tmp_path / "files.jsonl"
        user_entry = {"type": "user", "message": {"content": "look at files"}}
        assistant_entry = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "input": {"file_path": "/src/z.py"}},
                    {"type": "tool_use", "input": {"file_path": "/src/a.py"}},
                ]
            }
        }
        f.write_text(json.dumps(user_entry) + "\n" + json.dumps(assistant_entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        assert result["files_touched"] == sorted(result["files_touched"])

    def test_handles_exception_reading_file(self, tmp_path):
        # Directory instead of file — should return None gracefully
        d = tmp_path / "adir"
        d.mkdir()
        result = handoff_core.extract_conversation(str(d))
        assert result is None


# ---------------------------------------------------------------------------
# format_conversation_md
# ---------------------------------------------------------------------------

class TestFormatConversationMd:
    def test_empty_dict_returns_empty_string(self):
        assert handoff_core.format_conversation_md({}) == ""

    def test_none_returns_empty_string(self):
        assert handoff_core.format_conversation_md(None) == ""

    def test_formats_user_messages(self):
        conv = {"user_messages": ["Fix the bug"], "assistant_snippets": [], "files_touched": []}
        result = handoff_core.format_conversation_md(conv)
        assert "Recent User Messages" in result
        assert "Fix the bug" in result

    def test_formats_assistant_snippets(self):
        conv = {"user_messages": [], "assistant_snippets": ["Here is the fix"], "files_touched": []}
        result = handoff_core.format_conversation_md(conv)
        assert "Key Assistant Responses" in result
        assert "Here is the fix" in result

    def test_formats_files_touched(self):
        conv = {"user_messages": [], "assistant_snippets": [], "files_touched": ["/src/app.py"]}
        result = handoff_core.format_conversation_md(conv)
        assert "Files Touched" in result
        assert "/src/app.py" in result

    def test_truncates_long_user_messages(self):
        long_msg = "x" * 600
        conv = {"user_messages": [long_msg], "assistant_snippets": [], "files_touched": []}
        result = handoff_core.format_conversation_md(conv)
        assert "..." in result

    def test_truncates_long_assistant_snippets(self):
        long_snip = "y" * 400
        conv = {"user_messages": [], "assistant_snippets": [long_snip], "files_touched": []}
        result = handoff_core.format_conversation_md(conv)
        assert "..." in result

    def test_full_conversation_structure(self):
        conv = {
            "user_messages": ["Fix login bug"],
            "assistant_snippets": ["The issue is in auth.py"],
            "files_touched": ["/src/auth.py"],
        }
        result = handoff_core.format_conversation_md(conv)
        assert "Recent User Messages" in result
        assert "Key Assistant Responses" in result
        assert "Files Touched" in result
        assert "Fix login bug" in result
        assert "The issue is in auth.py" in result
        assert "/src/auth.py" in result

    def test_missing_keys_dont_crash(self):
        # Only user messages, missing others
        conv = {"user_messages": ["hello"]}
        result = handoff_core.format_conversation_md(conv)
        assert "hello" in result

    def test_numbered_user_messages(self):
        conv = {"user_messages": ["first task", "second task"], "assistant_snippets": [], "files_touched": []}
        result = handoff_core.format_conversation_md(conv)
        assert "1." in result
        assert "2." in result


# ---------------------------------------------------------------------------
# Coverage for previously missing lines
# ---------------------------------------------------------------------------

class TestMissingLineCoverage:
    def test_read_text_exception_returns_none(self, tmp_path, monkeypatch):
        """Lines 100-101: except Exception branch when read_text raises."""
        f = tmp_path / "unreadable.jsonl"
        f.write_text("dummy", encoding="utf-8")

        # Patch Path.read_text to raise so we actually hit the except block
        import builtins

        original_open = builtins.open

        def boom_read_text(self_path, *args, **kwargs):
            raise OSError("simulated permission denied")

        monkeypatch.setattr(Path, "read_text", boom_read_text)
        result = handoff_core.extract_conversation(str(f))
        assert result is None

    def test_user_content_non_str_non_list_gives_empty_text(self, tmp_path):
        """Line 131: else branch when user message content is neither str nor list."""
        f = tmp_path / "transcript.jsonl"
        # content is an integer — neither str nor list
        entry = {"type": "user", "message": {"content": 42}}
        # Add a second entry with a real message so the result is not None
        real_entry = {"type": "user", "message": {"content": "real message to keep result non-null"}}
        f.write_text(json.dumps(entry) + "\n" + json.dumps(real_entry) + "\n", encoding="utf-8")
        result = handoff_core.extract_conversation(str(f))
        # The integer-content entry should produce no user message text
        assert result is not None
        assert not any(msg == "" for msg in result["user_messages"])

    def test_assistant_non_dict_block_is_skipped(self, tmp_path):
        """Line 142: continue when a block in assistant content is not a dict."""
        f = tmp_path / "transcript.jsonl"
        user_entry = {"type": "user", "message": {"content": "help me with this task"}}
        # Mix a non-dict item (string) with a valid dict block
        assistant_entry = {
            "type": "assistant",
            "message": {
                "content": [
                    "this is a plain string not a dict",
                    {"type": "text", "text": "Here is the real assistant response"},
                ]
            },
        }
        f.write_text(
            json.dumps(user_entry) + "\n" + json.dumps(assistant_entry) + "\n",
            encoding="utf-8",
        )
        result = handoff_core.extract_conversation(str(f))
        assert result is not None
        # The valid dict block should still be captured
        assert any("real assistant response" in s for s in result["assistant_snippets"])
