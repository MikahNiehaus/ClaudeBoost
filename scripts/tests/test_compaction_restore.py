"""
Tests for scripts/compaction-restore.py (SessionStart hook).

Injects saved handoff context after compaction or /clear. Always exits 0.
"""
from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from helpers import SCRIPTS_DIR, run_hook

# Direct import for unit testing internal functions
_cr_spec = importlib.util.spec_from_file_location("compaction_restore", SCRIPTS_DIR / "compaction-restore.py")
_cr_mod = importlib.util.module_from_spec(_cr_spec)
_cr_spec.loader.exec_module(_cr_mod)


def _session(source: str, cwd: str = "/test/project") -> dict:
    return {
        "hook_event_name": "SessionStart",
        "session_id": "test",
        "source": source,
        "cwd": cwd,
    }


def _write_handoff(state_dir, memo: str, cwd: str = "/test/project", age_seconds: int = 0):
    from datetime import datetime, timezone, timedelta
    ts = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    handoff = {
        "session_id": "prev",
        "timestamp": ts.isoformat(),
        "cwd": cwd,
        "workspace_memo": memo,
        "conversation": {},
    }
    (state_dir / "handoff-latest.json").write_text(
        json.dumps(handoff), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "compaction-restore.py",
        _session("compact"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_on_unknown_source(boost_home):
    result = run_hook(
        "compaction-restore.py",
        _session("startup"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# source=compact: inject workspace memo
# ---------------------------------------------------------------------------

def test_injects_memo_on_compact(boost_home):
    state_dir = boost_home / "state"
    _write_handoff(state_dir, "### task-1\nStatus: in progress\nNext: write tests")

    result = run_hook(
        "compaction-restore.py",
        _session("compact"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "task-1" in ctx
    assert "COMPACTION" in ctx.upper()


def test_silent_on_compact_with_no_handoff(boost_home):
    # No handoff-latest.json
    result = run_hook(
        "compaction-restore.py",
        _session("compact"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# source=clear: age and cwd guards
# ---------------------------------------------------------------------------

def test_injects_on_clear_when_fresh_and_same_cwd(boost_home):
    state_dir = boost_home / "state"
    _write_handoff(state_dir, "### task-2\nStatus: done", cwd="/test/project", age_seconds=30)

    result = run_hook(
        "compaction-restore.py",
        _session("clear", cwd="/test/project"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    ctx = output.get("additionalContext", "")
    assert "task-2" in ctx


def test_silent_on_clear_when_stale(boost_home):
    state_dir = boost_home / "state"
    # 40 minutes old — past the 30-minute age guard
    _write_handoff(state_dir, "### task-old\nStale memo", age_seconds=2400)

    result = run_hook(
        "compaction-restore.py",
        _session("clear"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_silent_on_clear_when_different_cwd(boost_home):
    state_dir = boost_home / "state"
    _write_handoff(state_dir, "### task-x\nWrong project", cwd="/different/project", age_seconds=30)

    result = run_hook(
        "compaction-restore.py",
        _session("clear", cwd="/test/project"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# Direct import unit tests for internal functions
# ---------------------------------------------------------------------------

class TestLoadJson:
    def test_loads_valid_json(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        result = _cr_mod._load_json(p)
        assert result == {"key": "value"}

    def test_returns_empty_on_missing_file(self, tmp_path):
        result = _cr_mod._load_json(tmp_path / "nonexistent.json")
        assert result == {}

    def test_returns_empty_on_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("NOT JSON", encoding="utf-8")
        result = _cr_mod._load_json(p)
        assert result == {}


class TestLoadCompactMemo:
    def test_returns_empty_when_file_missing(self, tmp_path):
        result = _cr_mod._load_compact_memo(tmp_path)
        assert result == {}

    def test_normalizes_memo_key(self, tmp_path):
        p = tmp_path / "compaction-memo.json"
        p.write_text(json.dumps({"memo": "workspace notes here"}), encoding="utf-8")
        result = _cr_mod._load_compact_memo(tmp_path)
        assert result["workspace_memo"] == "workspace notes here"

    def test_preserves_workspace_memo_if_present(self, tmp_path):
        p = tmp_path / "compaction-memo.json"
        p.write_text(json.dumps({"workspace_memo": "already normalized"}), encoding="utf-8")
        result = _cr_mod._load_compact_memo(tmp_path)
        assert result["workspace_memo"] == "already normalized"


class TestAgeOk:
    def test_fresh_timestamp_passes(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        assert _cr_mod._age_ok({"timestamp": ts}) is True

    def test_stale_timestamp_fails(self):
        ts = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
        assert _cr_mod._age_ok({"timestamp": ts}) is False

    def test_missing_timestamp_fails(self):
        assert _cr_mod._age_ok({}) is False

    def test_naive_timestamp_gets_utc(self):
        # Without timezone info — should still work
        ts = (datetime.utcnow() - timedelta(seconds=60)).isoformat()
        assert _cr_mod._age_ok({"timestamp": ts}) is True

    def test_bad_timestamp_returns_false(self):
        assert _cr_mod._age_ok({"timestamp": "not-a-date"}) is False


class TestCwdOk:
    def test_matching_cwd_passes(self):
        assert _cr_mod._cwd_ok({"cwd": "/project/foo"}, "/project/foo") is True

    def test_different_cwd_fails(self):
        assert _cr_mod._cwd_ok({"cwd": "/project/foo"}, "/project/bar") is False

    def test_empty_handoff_cwd_allows(self):
        assert _cr_mod._cwd_ok({}, "/project/foo") is True

    def test_empty_session_cwd_allows(self):
        assert _cr_mod._cwd_ok({"cwd": "/project/foo"}, "") is True

    def test_windows_paths_normalized(self):
        assert _cr_mod._cwd_ok({"cwd": "C:\\Users\\foo\\project"}, "C:/Users/foo/project") is True


class TestFormatConversation:
    def test_empty_conversation_returns_empty(self):
        result = _cr_mod._format_conversation({})
        assert result == ""

    def test_includes_user_messages(self):
        conv = {"user_messages": ["Hello", "What does this do?"], "files_touched": []}
        result = _cr_mod._format_conversation(conv)
        assert "Hello" in result
        assert "What does this do?" in result

    def test_includes_files_touched(self):
        conv = {"user_messages": [], "files_touched": ["src/foo.py", "tests/test_foo.py"]}
        result = _cr_mod._format_conversation(conv)
        assert "src/foo.py" in result
        assert "tests/test_foo.py" in result

    def test_truncates_long_messages(self):
        conv = {"user_messages": ["x" * 600], "files_touched": []}
        result = _cr_mod._format_conversation(conv)
        assert "..." in result


class TestMainDirectly:
    def test_compact_falls_back_to_memo_json(self, tmp_path):
        """When no handoff-latest.json, falls back to compaction-memo.json."""
        (tmp_path / "state").mkdir(parents=True)
        memo = {"workspace_memo": "Memo from old compact"}
        (tmp_path / "state" / "compaction-memo.json").write_text(json.dumps(memo), encoding="utf-8")

        result = run_hook(
            "compaction-restore.py",
            _session("compact"),
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "Memo from old compact" in output["additionalContext"]

    def test_compact_with_conversation_section(self, tmp_path):
        """When handoff has conversation data, it appears in the output."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        ts = datetime.now(timezone.utc).isoformat()
        handoff = {
            "timestamp": ts,
            "cwd": "/test/project",
            "workspace_memo": "Working on feature X",
            "conversation": {
                "user_messages": ["Can you fix the bug?", "Also add a test."],
                "files_touched": ["src/foo.py"],
            },
        }
        (state_dir / "handoff-latest.json").write_text(json.dumps(handoff), encoding="utf-8")

        result = run_hook(
            "compaction-restore.py",
            _session("compact"),
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        ctx = output["additionalContext"]
        assert "Can you fix the bug?" in ctx
        assert "src/foo.py" in ctx

    def test_main_handles_bad_json_stdin(self, tmp_path):
        """Bad JSON on stdin → treated as no input, exits 0."""
        result = run_hook(
            "compaction-restore.py",
            {},  # will be overridden below
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_clear_with_no_handoff_exits_0(self, boost_home):
        result = run_hook(
            "compaction-restore.py",
            _session("clear"),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == b""

    def test_bad_json_stdin_treated_as_no_input(self, tmp_path):
        """Lines 101-102: invalid JSON on stdin falls back to empty dict, exits 0."""
        import subprocess
        script = SCRIPTS_DIR / "compaction-restore.py"
        env = {**__import__("os").environ, "CLAUDEBOOST_HOME": str(tmp_path)}
        result = subprocess.run(
            [__import__("sys").executable, str(script)],
            input=b"NOT VALID JSON {{{",
            capture_output=True,
            env=env,
        )
        # Invalid JSON is caught; script falls back to no-op source="" and exits 0.
        assert result.returncode == 0
        assert result.stdout.strip() == b""

    def test_compact_data_with_no_workspace_memo_exits_silently(self, tmp_path):
        """Line 131: data loaded but workspace_memo is absent/empty — no output."""
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True)
        # Write a handoff with no workspace_memo and no memo key
        (state_dir / "handoff-latest.json").write_text(
            json.dumps({"session_id": "s1", "cwd": str(tmp_path)}),
            encoding="utf-8",
        )
        result = run_hook(
            "compaction-restore.py",
            _session("compact"),
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == b""


class TestInvalidJsonStdin:
    """Lines 101-102: invalid JSON on stdin -> except Exception -> hook_input = {}."""

    def _load_mod(self):
        import importlib.util
        from pathlib import Path
        spec = importlib.util.spec_from_file_location(
            "compaction_restore",
            Path(__file__).resolve().parent.parent / "compaction-restore.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_invalid_json_on_stdin_exits_cleanly(self, tmp_path, monkeypatch):
        """Lines 101-102: json.loads(raw) raises -> except Exception: hook_input = {}."""
        import io
        mod = self._load_mod()
        monkeypatch.setattr(mod.sys, "stdin", io.StringIO("NOT VALID JSON {{{"))
        monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
        (tmp_path / "state").mkdir(parents=True)
        result = mod.main()
        assert result == 0
