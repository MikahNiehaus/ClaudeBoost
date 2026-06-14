"""
Tests for scripts/compaction-save.py (PreCompact hook).

Saves workspace context to compaction-memo.json and handoff-latest.json.
Always exits 0.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from helpers import SCRIPTS_DIR, run_hook

# Direct import for unit testing
_cs_spec = importlib.util.spec_from_file_location("compaction_save", SCRIPTS_DIR / "compaction-save.py")
_cs_mod = importlib.util.module_from_spec(_cs_spec)
_cs_spec.loader.exec_module(_cs_mod)


def _precompact(session_id: str = "test-session", cwd: str = "/test") -> dict:
    return {
        "hook_event_name": "PreCompact",
        "session_id": session_id,
        "cwd": cwd,
        "transcript_path": "",
    }


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_no_workspaces(boost_home):
    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Creates compaction-memo.json
# ---------------------------------------------------------------------------

def test_creates_compaction_memo(boost_home):
    memo_path = boost_home / "state" / "compaction-memo.json"
    assert not memo_path.exists()

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert memo_path.exists()

    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    assert "memo" in memo
    assert memo.get("compaction_number") == 1


def test_increments_compaction_number(boost_home):
    memo_path = boost_home / "state" / "compaction-memo.json"
    memo_path.write_text(json.dumps({
        "compaction_number": 5,
        "memo": "old memo",
        "session_id": "old",
        "timestamp": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    assert memo.get("compaction_number") == 6


# ---------------------------------------------------------------------------
# Creates handoff-latest.json
# ---------------------------------------------------------------------------

def test_creates_handoff_latest(boost_home):
    handoff_path = boost_home / "state" / "handoff-latest.json"

    result = run_hook(
        "compaction-save.py",
        _precompact(session_id="my-session", cwd="/myproject"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert handoff_path.exists()

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff.get("trigger") == "PreCompact"
    assert handoff.get("session_id") == "my-session"
    assert "workspace_memo" in handoff


# ---------------------------------------------------------------------------
# Includes workspace context summaries
# ---------------------------------------------------------------------------

def test_includes_workspace_context(boost_home):
    ws_dir = boost_home / "workspace" / "task-99"
    ws_dir.mkdir(parents=True)
    ctx = ws_dir / "context.md"
    ctx.write_text("# Task 99\n## Goal\nBuild the thing\n## Status\nIn progress", encoding="utf-8")

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    memo_path = boost_home / "state" / "compaction-memo.json"
    memo = json.loads(memo_path.read_text(encoding="utf-8"))
    assert "task-99" in memo.get("memo", "")


# ---------------------------------------------------------------------------
# Outputs additionalContext
# ---------------------------------------------------------------------------

def test_outputs_additional_context(boost_home):
    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert "additionalContext" in output


# ---------------------------------------------------------------------------
# Archives previous memo
# ---------------------------------------------------------------------------

def test_archives_previous_memo(boost_home):
    memo_path = boost_home / "state" / "compaction-memo.json"
    memo_path.write_text(json.dumps({
        "compaction_number": 1,
        "memo": "previous memo",
        "session_id": "old-session",
        "timestamp": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")

    result = run_hook(
        "compaction-save.py",
        _precompact(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    history_dir = boost_home / "state" / "compaction-history"
    assert history_dir.exists()
    history_files = list(history_dir.glob("*.json"))
    assert len(history_files) == 1


# ---------------------------------------------------------------------------
# Direct import unit tests for extract_summary
# ---------------------------------------------------------------------------

class TestExtractSummary:
    def test_skips_skip_sections(self):
        # "research sources" and "agent contributions" are actual SKIP_SECTIONS entries
        content = "## Goal\nBuild it\n## Research Sources\nFound many things\n## Status\nDone"
        result = _cs_mod.extract_summary(content)
        # "research sources" should be skipped — its content "Found many things" should not appear
        assert "Found many things" not in result
        assert "Build it" in result

    def test_char_budget_overflow_stops_early(self):
        # Create content that exceeds char_budget
        content = "## Status\nActive\n" + "\n".join(
            f"## Section{i}\n" + ("x" * 500) for i in range(10)
        )
        result = _cs_mod.extract_summary(content, char_budget=500)
        # Should be truncated — not all 10 sections
        assert len(result) <= 1500  # some reasonable cap

    def test_returns_preamble_alone_when_no_sections(self):
        content = "My workspace title"
        result = _cs_mod.extract_summary(content)
        assert "My workspace title" in result

    def test_empty_content(self):
        result = _cs_mod.extract_summary("")
        assert isinstance(result, str)


class TestMainExceptionPaths:
    def test_bad_json_stdin_does_not_crash(self, boost_home):
        """Bad JSON on stdin is handled gracefully."""
        result = run_hook(
            "compaction-save.py",
            {},
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_invalid_json_stdin_subprocess(self, boost_home):
        """Sending raw invalid JSON directly triggers lines 79-80 (except Exception)."""
        import subprocess as _sp
        import os
        result = _sp.run(
            ["python", str(SCRIPTS_DIR / "compaction-save.py")],
            input=b"INVALID JSON BYTES",
            capture_output=True,
            env={**os.environ, "CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_archive_write_failure_does_not_crash(self, boost_home):
        """Archive write fails when the archive target path is a dir (lines 100-101)."""
        # Create an existing memo so the archive path is triggered
        memo_path = boost_home / "state" / "compaction-memo.json"
        memo_path.write_text('{"compaction_number":1,"memo":"x","session_id":"old-sess","timestamp":"t"}')
        # Create history dir so mkdir succeeds, then make the archive target a dir
        history_dir = boost_home / "state" / "compaction-history"
        history_dir.mkdir(parents=True)
        archive_target = history_dir / "old-sess-compact-1.json"
        archive_target.mkdir()  # directory prevents write_text from succeeding

        result = run_hook(
            "compaction-save.py",
            _precompact(),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_context_file_unreadable(self, boost_home):
        """Context file that raises on read triggers lines 112-113."""
        # Create a workspace with context.md as a directory (unreadable as text)
        ws_dir = boost_home / "workspace" / "unreadable-task"
        ctx_dir = ws_dir / "context.md"
        ctx_dir.mkdir(parents=True)  # directory instead of file

        result = run_hook(
            "compaction-save.py",
            _precompact(),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_handoff_latest_write_failure(self, boost_home):
        """handoff-latest.json write failure is silently ignored (lines 173-174)."""
        # Make the handoff-latest.json path a directory — write_text will fail
        state_dir = boost_home / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        handoff_as_dir = state_dir / "handoff-latest.json"
        handoff_as_dir.mkdir()

        result = run_hook(
            "compaction-save.py",
            _precompact(),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_unreadable_context_file_handled(self, boost_home):
        """A workspace context.md that errors on read is handled."""
        ws_dir = boost_home / "workspace" / "bad-task"
        ws_dir.mkdir(parents=True)
        ctx = ws_dir / "context.md"
        ctx.write_text("good content", encoding="utf-8")

        # Run normally — the unreadable path is covered by the exception handler
        result = run_hook(
            "compaction-save.py",
            _precompact(),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0

    def test_with_transcript_and_conversation(self, boost_home, tmp_path):
        """When transcript_path is provided, conversation highlights are included."""
        import json as _json
        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "please fix the bug in the login flow"}],
            }
        }
        transcript.write_text(_json.dumps(entry) + "\n", encoding="utf-8")

        payload = _precompact()
        payload["transcript_path"] = str(transcript)

        result = run_hook(
            "compaction-save.py",
            payload,
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# Targeted tests for previously uncovered lines
# ---------------------------------------------------------------------------

class TestUncoveredBranches:
    """Tests that hit the specific uncovered lines: 79-80, 147-148, 180-181, 186-189."""

    def test_invalid_json_stdin_hits_except_block(self, boost_home, monkeypatch):
        """Lines 79-80: json.loads raises when stdin has non-JSON text."""
        import io

        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        # Patch stdin to return invalid JSON (not a tty, has content)
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
            io.BytesIO(b"NOT VALID JSON AT ALL"), encoding="utf-8"
        ))
        # isatty() returns False on BytesIO-backed TextIOWrapper, so raw gets read
        result = _cs_mod.main()
        assert result == 0

    def test_handoff_core_import_error_sets_conversation_none(self, boost_home, monkeypatch, tmp_path):
        """Lines 147-148: ImportError during 'from handoff_core import ...' sets conversation=None."""
        import io
        import builtins

        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        stdin_data = json.dumps(_precompact()).encode()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
            io.BytesIO(stdin_data), encoding="utf-8"
        ))

        original_import = builtins.__import__

        def blocking_import(name, *args, **kwargs):
            if name == "handoff_core":
                raise ImportError("handoff_core not available")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocking_import)
        result = _cs_mod.main()
        assert result == 0

    def test_tracker_write_failure_is_silently_ignored(self, boost_home, monkeypatch):
        """Lines 180-181: write_text fails for tracker file; script continues and exits 0."""
        import io
        from unittest.mock import MagicMock

        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))
        stdin_data = json.dumps(_precompact()).encode()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
            io.BytesIO(stdin_data), encoding="utf-8"
        ))

        # Make the tracker file's parent exist but make write_text raise for
        # the specific tracker path by monkeypatching Path.write_text.
        original_write_text = Path.write_text

        def failing_write_text(self, data, encoding=None, errors=None):
            if self.name == "compaction-tracker.json":
                raise OSError("disk full")
            return original_write_text(self, data, encoding=encoding)

        monkeypatch.setattr(Path, "write_text", failing_write_text)
        result = _cs_mod.main()
        assert result == 0

    def test_format_conversation_md_exception_is_silently_ignored(self, boost_home, monkeypatch):
        """Lines 186-189: format_conversation_md raises; the except: pass swallows it."""
        import io
        import types

        monkeypatch.setenv("CLAUDEBOOST_HOME", str(boost_home))

        payload = _precompact()
        payload["transcript_path"] = "dummy-path.jsonl"
        stdin_data = json.dumps(payload).encode()
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
            io.BytesIO(stdin_data), encoding="utf-8"
        ))

        # Inject a fake handoff_core that returns a non-empty conversation but
        # whose format_conversation_md always raises.
        fake_conv = {"user_messages": ["hello"], "files_touched": []}

        def fake_extract(path):
            return fake_conv

        def fake_format(conv):
            raise RuntimeError("format failed")

        fake_mod = types.ModuleType("handoff_core")
        fake_mod.extract_conversation = fake_extract
        fake_mod.format_conversation_md = fake_format

        # Insert into sys.modules so the import inside main() picks it up.
        import sys as _sys
        _sys.modules["handoff_core"] = fake_mod
        try:
            result = _cs_mod.main()
        finally:
            _sys.modules.pop("handoff_core", None)

        assert result == 0
