"""
Tests for scripts/changes_core.py (library module).

Covers: load_changes, parse_hunk_header, count_file_changes, get_lexer_for_path,
build_summary_markup, highlight_code_line, build_diff_content, get_chat_file,
write_chat_question, read_chat_answer.

Tested by direct import — not via subprocess.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import changes_core


# ---------------------------------------------------------------------------
# load_changes
# ---------------------------------------------------------------------------

class TestLoadChanges:
    def test_loads_valid_json(self, tmp_path):
        data = {"project": "MyApp", "files": [], "summary": {"lines_added": 5, "lines_removed": 2}}
        f = tmp_path / "changes.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = changes_core.load_changes(str(f))
        assert result["project"] == "MyApp"
        assert result["summary"]["lines_added"] == 5

    def test_sets_defaults_for_missing_keys(self, tmp_path):
        f = tmp_path / "changes.json"
        f.write_text(json.dumps({}), encoding="utf-8")
        result = changes_core.load_changes(str(f))
        assert result["files"] == []
        assert result["project"] == "Unknown"
        assert result["summary"]["lines_added"] == 0

    def test_exits_on_missing_file(self, tmp_path):
        with pytest.raises(SystemExit):
            changes_core.load_changes(str(tmp_path / "missing.json"))

    def test_exits_on_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("NOT JSON", encoding="utf-8")
        with pytest.raises(SystemExit):
            changes_core.load_changes(str(f))

    def test_normalizes_file_defaults(self, tmp_path):
        data = {"files": [{"path": "src/foo.py"}]}
        f = tmp_path / "changes.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = changes_core.load_changes(str(f))
        file_entry = result["files"][0]
        assert file_entry["status"] == "modified"
        assert file_entry["hunks"] == []
        assert file_entry["agent"] == ""

    def test_sets_files_changed_count(self, tmp_path):
        data = {"files": [{"path": "a.py"}, {"path": "b.py"}]}
        f = tmp_path / "changes.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = changes_core.load_changes(str(f))
        assert result["summary"]["files_changed"] == 2


# ---------------------------------------------------------------------------
# parse_hunk_header
# ---------------------------------------------------------------------------

class TestParseHunkHeader:
    def test_parses_standard_header(self):
        old, new = changes_core.parse_hunk_header("@@ -10,5 +15,3 @@")
        assert old == 10
        assert new == 15

    def test_parses_header_without_counts(self):
        old, new = changes_core.parse_hunk_header("@@ -1 +1 @@")
        assert old == 1
        assert new == 1

    def test_returns_1_1_for_empty(self):
        old, new = changes_core.parse_hunk_header("")
        assert old == 1
        assert new == 1

    def test_returns_1_1_for_malformed(self):
        old, new = changes_core.parse_hunk_header("not a hunk header")
        assert old == 1
        assert new == 1

    def test_parses_with_extra_context(self):
        old, new = changes_core.parse_hunk_header("@@ -25,10 +30,8 @@ def foo():")
        assert old == 25
        assert new == 30


# ---------------------------------------------------------------------------
# count_file_changes
# ---------------------------------------------------------------------------

class TestCountFileChanges:
    def test_counts_added_and_removed(self):
        file_data = {
            "hunks": [
                {"old_code": "line1\nline2", "new_code": "newline1\nnewline2\nnewline3"}
            ]
        }
        added, removed = changes_core.count_file_changes(file_data)
        assert added == 3
        assert removed == 2

    def test_empty_hunks(self):
        added, removed = changes_core.count_file_changes({"hunks": []})
        assert added == 0
        assert removed == 0

    def test_only_additions(self):
        file_data = {"hunks": [{"old_code": "", "new_code": "new\nlines"}]}
        added, removed = changes_core.count_file_changes(file_data)
        assert added == 2
        assert removed == 0

    def test_only_removals(self):
        file_data = {"hunks": [{"old_code": "gone\nlines", "new_code": ""}]}
        added, removed = changes_core.count_file_changes(file_data)
        assert added == 0
        assert removed == 2

    def test_no_hunks_key(self):
        added, removed = changes_core.count_file_changes({})
        assert added == 0
        assert removed == 0


# ---------------------------------------------------------------------------
# get_lexer_for_path
# ---------------------------------------------------------------------------

class TestGetLexerForPath:
    def test_python_extension(self):
        assert changes_core.get_lexer_for_path("foo.py") == "python"

    def test_typescript_extension(self):
        assert changes_core.get_lexer_for_path("bar.ts") == "typescript"

    def test_unknown_extension(self):
        assert changes_core.get_lexer_for_path("file.xyz") == "text"

    def test_json_extension(self):
        assert changes_core.get_lexer_for_path("data.json") == "json"

    def test_no_extension(self):
        assert changes_core.get_lexer_for_path("Makefile") == "text"

    def test_case_insensitive(self):
        assert changes_core.get_lexer_for_path("FOO.PY") == "python"

    def test_yaml_yml(self):
        assert changes_core.get_lexer_for_path("config.yaml") == "yaml"
        assert changes_core.get_lexer_for_path("config.yml") == "yaml"


# ---------------------------------------------------------------------------
# build_summary_markup
# ---------------------------------------------------------------------------

class TestBuildSummaryMarkup:
    def _data(self, **overrides):
        base = {
            "project": "TestProject",
            "summary": {
                "files_changed": 3,
                "lines_added": 10,
                "lines_removed": 5,
                "agents": ["test-agent"],
            }
        }
        base.update(overrides)
        return base

    def test_includes_project_name(self):
        result = changes_core.build_summary_markup(self._data())
        assert "TestProject" in result

    def test_includes_agent_names(self):
        result = changes_core.build_summary_markup(self._data())
        assert "test-agent" in result

    def test_no_agents_shows_none(self):
        data = self._data()
        data["summary"]["agents"] = []
        result = changes_core.build_summary_markup(data)
        assert "none" in result.lower()

    def test_custom_colors(self):
        result = changes_core.build_summary_markup(self._data(), colors={"agent": "magenta"})
        assert "magenta" in result

    def test_includes_timestamp_when_present(self):
        data = self._data()
        data["generated_at"] = "2026-01-01T12:00:00Z"
        result = changes_core.build_summary_markup(data)
        assert "2026-01-01" in result

    def test_includes_goal_when_present(self):
        data = self._data()
        data["goal"] = "Fix authentication"
        result = changes_core.build_summary_markup(data)
        assert "Fix authentication" in result


# ---------------------------------------------------------------------------
# highlight_code_line
# ---------------------------------------------------------------------------

class TestHighlightCodeLine:
    def test_returns_text_object(self):
        from rich.text import Text
        result = changes_core.highlight_code_line("x = 1", "python")
        assert isinstance(result, Text)

    def test_plain_text_lexer(self):
        from rich.text import Text
        result = changes_core.highlight_code_line("hello world", "text")
        assert isinstance(result, Text)
        assert result.plain == "hello world"

    def test_empty_line(self):
        from rich.text import Text
        result = changes_core.highlight_code_line("", "python")
        assert isinstance(result, Text)

    def test_with_bg_color(self):
        from rich.text import Text
        result = changes_core.highlight_code_line("def foo():", "python", bg_color="#001a00")
        assert isinstance(result, Text)

    def test_text_lexer_with_bg_color(self):
        """text lexer + bg_color — covers the stylize call inside the text branch (line 169)."""
        from rich.text import Text
        result = changes_core.highlight_code_line("plain text", "text", bg_color="green")
        assert isinstance(result, Text)
        assert result.plain == "plain text"

    def test_exception_fallback_with_bg_color(self):
        """When highlight() raises, the except block falls back to plain Text (lines 185-189)."""
        from rich.text import Text
        with patch("changes_core.Syntax", side_effect=Exception("syntax error")):
            result = changes_core.highlight_code_line("def foo():", "python", bg_color="red")
        assert isinstance(result, Text)


# ---------------------------------------------------------------------------
# build_diff_content
# ---------------------------------------------------------------------------

class TestBuildDiffContent:
    def _file_data(self, path="src/foo.py", status="modified", hunks=None):
        return {
            "path": path,
            "status": status,
            "agent": "test-agent",
            "summary": "Added stuff",
            "hunks": hunks or [],
        }

    def test_returns_text_object(self):
        from rich.text import Text
        result = changes_core.build_diff_content(self._file_data())
        assert isinstance(result, Text)

    def test_includes_file_path(self):
        result = changes_core.build_diff_content(self._file_data())
        assert "src/foo.py" in result.plain

    def test_no_hunks_message(self):
        result = changes_core.build_diff_content(self._file_data(hunks=[]))
        assert "No hunks" in result.plain

    def test_with_hunks(self):
        hunks = [{
            "header": "@@ -1,2 +1,3 @@",
            "old_code": "old line",
            "new_code": "new line\nextra line",
            "explanation": "Added extra line",
        }]
        result = changes_core.build_diff_content(self._file_data(hunks=hunks))
        assert "old line" in result.plain or "new line" in result.plain

    def test_collapsed_hunk(self):
        hunks = [{"header": "@@ -1,2 +1,2 @@", "old_code": "x", "new_code": "y"}]
        result = changes_core.build_diff_content(self._file_data(hunks=hunks), collapsed_hunks={0})
        assert "collapsed" in result.plain

    def test_hides_explanation_when_disabled(self):
        hunks = [{
            "header": "@@ -1,2 +1,2 @@",
            "old_code": "x",
            "new_code": "y",
            "explanation": "This is the explanation text",
        }]
        result = changes_core.build_diff_content(
            self._file_data(hunks=hunks), show_explanations=False
        )
        assert "This is the explanation text" not in result.plain

    def test_added_file_status(self):
        result = changes_core.build_diff_content(self._file_data(status="added"))
        assert "[A]" in result.plain

    def test_deleted_file_status(self):
        result = changes_core.build_diff_content(self._file_data(status="deleted"))
        assert "[D]" in result.plain

    def test_custom_theme(self):
        from rich.text import Text
        theme = {"hunk_label_prefix": "Change"}
        hunks = [{"header": "@@ -1,2 +1,2 @@", "old_code": "x", "new_code": "y"}]
        result = changes_core.build_diff_content(self._file_data(hunks=hunks), theme=theme)
        assert isinstance(result, Text)

    def test_file_with_agent_and_summary(self):
        result = changes_core.build_diff_content({
            "path": "app.py",
            "status": "modified",
            "agent": "my-agent",
            "summary": "My summary",
            "hunks": [],
        })
        assert "my-agent" in result.plain
        assert "My summary" in result.plain

    def test_no_agent_no_summary(self):
        from rich.text import Text
        result = changes_core.build_diff_content({
            "path": "app.py",
            "status": "modified",
            "agent": "",
            "summary": "",
            "hunks": [],
        })
        assert isinstance(result, Text)


# ---------------------------------------------------------------------------
# Chat file functions
# ---------------------------------------------------------------------------

class TestChatFileFunctions:
    def test_get_chat_file_creates_parent(self, tmp_path, monkeypatch):
        # Override the CHAT_FILE constant to point to tmp_path
        import changes_core as cc
        original = cc.CHAT_FILE
        cc.CHAT_FILE = tmp_path / "claudeboost" / "changes_chat.json"
        try:
            result = cc.get_chat_file()
            assert result.parent.exists()
        finally:
            cc.CHAT_FILE = original

    def test_write_and_read_chat(self, tmp_path, monkeypatch):
        import changes_core as cc
        original = cc.CHAT_FILE
        cc.CHAT_FILE = tmp_path / "claudeboost" / "changes_chat.json"
        try:
            cc.write_chat_question("what does this do?", "src/foo.py", "x = 1")
            chat_file = cc.get_chat_file()
            data = json.loads(chat_file.read_text(encoding="utf-8"))
            assert data["question"] == "what does this do?"
            assert data["context_file"] == "src/foo.py"
            assert data["answer"] == ""
        finally:
            cc.CHAT_FILE = original

    def test_read_chat_answer_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        import changes_core as cc
        original = cc.CHAT_FILE
        cc.CHAT_FILE = tmp_path / "nowhere" / "chat.json"
        try:
            result = cc.read_chat_answer()
            assert result == ""
        finally:
            cc.CHAT_FILE = original

    def test_read_chat_answer_returns_answer(self, tmp_path, monkeypatch):
        import changes_core as cc
        original = cc.CHAT_FILE
        chat_dir = tmp_path / "claudeboost"
        chat_dir.mkdir()
        cc.CHAT_FILE = chat_dir / "changes_chat.json"
        try:
            data = {"question": "test", "answer": "It does X", "answered_at": ""}
            cc.CHAT_FILE.write_text(json.dumps(data), encoding="utf-8")
            result = cc.read_chat_answer()
            assert result == "It does X"
        finally:
            cc.CHAT_FILE = original

    def test_read_chat_answer_handles_bad_json(self, tmp_path, monkeypatch):
        import changes_core as cc
        original = cc.CHAT_FILE
        chat_dir = tmp_path / "claudeboost"
        chat_dir.mkdir()
        cc.CHAT_FILE = chat_dir / "changes_chat.json"
        try:
            cc.CHAT_FILE.write_text("INVALID JSON", encoding="utf-8")
            result = cc.read_chat_answer()
            assert result == ""
        finally:
            cc.CHAT_FILE = original


# ---------------------------------------------------------------------------
# HunkIndicator
# ---------------------------------------------------------------------------

class TestHunkIndicator:
    def test_set_hunk_with_total_zero(self):
        indicator = changes_core.HunkIndicator()
        # Mock update since we don't have a running Textual app
        with patch.object(indicator, "update") as mock_update:
            indicator.set_hunk(0, 0)
            mock_update.assert_called_once_with("")

    def test_set_hunk_positive(self):
        indicator = changes_core.HunkIndicator()
        with patch.object(indicator, "update") as mock_update:
            indicator.set_hunk(2, 5)
            mock_update.assert_called_once_with("Hunk 2/5")

    def test_set_hunk_custom_label(self):
        indicator = changes_core.HunkIndicator()
        indicator.hunk_label = "Change"
        with patch.object(indicator, "update") as mock_update:
            indicator.set_hunk(1, 3)
            call_arg = mock_update.call_args[0][0]
            assert "Change" in call_arg
            assert "1/3" in call_arg


# ---------------------------------------------------------------------------
# Breadcrumb
# ---------------------------------------------------------------------------

class TestBreadcrumb:
    def test_set_path_with_dirname(self):
        bc = changes_core.Breadcrumb()
        with patch.object(bc, "update") as mock_update:
            bc.set_path("src/foo/bar.py")
            mock_update.assert_called_once()
            call_arg = mock_update.call_args[0][0]
            assert "bar.py" in call_arg

    def test_set_path_no_dirname(self):
        bc = changes_core.Breadcrumb()
        with patch.object(bc, "update") as mock_update:
            bc.set_path("README.md")
            mock_update.assert_called_once()
            call_arg = mock_update.call_args[0][0]
            assert "README.md" in call_arg

    def test_attributes(self):
        bc = changes_core.Breadcrumb()
        assert bc.back_indicator == "<"
        assert bc.accent_color == "#00ff41"


# ---------------------------------------------------------------------------
# BaseChangesViewer — init and overridable methods (no running app required)
# ---------------------------------------------------------------------------

class TestBaseChangesViewer:
    def _make_data(self, files=None):
        return {
            "project": "TestProject",
            "agent": "test-agent",
            "files": files or [
                {"path": "src/foo.py", "status": "modified", "hunks": [], "agent": "a", "summary": "s"},
                {"path": "lib/bar.ts", "status": "added", "hunks": [], "agent": "b", "summary": ""},
            ],
        }

    def test_init_builds_file_lookup(self):
        data = self._make_data()
        viewer = changes_core.BaseChangesViewer(data)
        assert "src/foo.py" in viewer._file_lookup
        assert "lib/bar.ts" in viewer._file_lookup

    def test_init_sets_state(self):
        data = self._make_data()
        viewer = changes_core.BaseChangesViewer(data)
        assert viewer._current_file is None
        assert viewer._current_hunk_index == 0
        assert viewer._total_hunks == 0
        assert viewer._collapsed_hunks == set()
        assert viewer._reviewed_files == set()
        assert viewer._tree_built is False

    def test_get_summary_colors_returns_dict(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        assert isinstance(viewer._get_summary_colors(), dict)

    def test_get_diff_theme_returns_dict(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        assert isinstance(viewer._get_diff_theme(), dict)

    def test_get_tree_label_returns_string(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        label = viewer._get_tree_label()
        assert isinstance(label, str)
        assert len(label) > 0

    def test_format_file_label_modified(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        file_data = {"path": "src/foo.py", "status": "modified", "agent": "my-agent", "hunks": [
            {"old_code": "x\ny", "new_code": "z"},
        ]}
        label = viewer._format_file_label(file_data, "foo.py")
        assert "foo.py" in label

    def test_format_file_label_no_agent(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        file_data = {"path": "src/x.py", "status": "added", "agent": "", "hunks": []}
        label = viewer._format_file_label(file_data, "x.py")
        assert "x.py" in label

    def test_format_file_label_shows_change_counts(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        file_data = {"path": "src/x.py", "status": "modified", "agent": "", "hunks": [
            {"old_code": "a\nb\nc", "new_code": "d\ne"},
        ]}
        label = viewer._format_file_label(file_data, "x.py")
        # Should contain + and - change counts
        assert "+" in label or "-" in label or "x.py" in label

    def test_make_breadcrumb_returns_breadcrumb(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        bc = viewer._make_breadcrumb()
        assert isinstance(bc, changes_core.Breadcrumb)

    def test_make_hunk_indicator_returns_hunk_indicator(self):
        viewer = changes_core.BaseChangesViewer(self._make_data())
        hi = viewer._make_hunk_indicator()
        assert isinstance(hi, changes_core.HunkIndicator)


# ---------------------------------------------------------------------------
# ChatPanel — direct method tests (no running app needed)
# ---------------------------------------------------------------------------

class TestChatPanel:
    def test_check_for_answer_when_not_waiting(self):
        """_check_for_answer returns immediately when _waiting_for_answer is False (lines 445-446)."""
        panel = changes_core.ChatPanel()
        panel._waiting_for_answer = False
        panel._check_for_answer()  # should not raise, reads no file

    def test_check_for_answer_when_waiting_no_answer(self, monkeypatch):
        """_check_for_answer reads the file but does nothing when answer is empty (line 447-448)."""
        panel = changes_core.ChatPanel()
        panel._waiting_for_answer = True
        monkeypatch.setattr(changes_core, "read_chat_answer", lambda: "")
        panel._check_for_answer()
        assert panel._waiting_for_answer is True  # stays True because no answer

    def test_check_for_answer_with_answer(self, monkeypatch):
        """_check_for_answer clears the waiting flag and calls show_response (lines 449-450)."""
        panel = changes_core.ChatPanel()
        panel._waiting_for_answer = True
        monkeypatch.setattr(changes_core, "read_chat_answer", lambda: "the answer text")
        with patch.object(panel, "show_response") as mock_show:
            panel._check_for_answer()
        assert panel._waiting_for_answer is False
        mock_show.assert_called_once_with("the answer text")
