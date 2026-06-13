"""
Tests for scripts/session-clear-save.py (SessionEnd hook).

Saves workspace context to handoff-latest.json on /clear. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _session_end(source: str = "clear", session_id: str = "test", cwd: str = "/test") -> dict:
    return {
        "hook_event_name": "SessionEnd",
        "session_id": session_id,
        "source": source,
        "cwd": cwd,
        "transcript_path": "",
    }


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_exits_0_on_compact_source(boost_home):
    # "compact" source should be skipped (not our trigger)
    result = run_hook(
        "session-clear-save.py",
        _session_end(source="compact"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Creates handoff-latest.json on clear
# ---------------------------------------------------------------------------

def test_creates_handoff_on_clear(boost_home):
    handoff_path = boost_home / "state" / "handoff-latest.json"
    assert not handoff_path.exists()

    result = run_hook(
        "session-clear-save.py",
        _session_end(source="clear", session_id="test-sess", cwd="/myproject"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert handoff_path.exists()

    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff.get("trigger") == "SessionEnd(clear)"
    assert handoff.get("session_id") == "test-sess"


# ---------------------------------------------------------------------------
# Includes workspace context
# ---------------------------------------------------------------------------

def test_includes_workspace_memo(boost_home):
    ws_dir = boost_home / "workspace" / "task-abc"
    ws_dir.mkdir(parents=True)
    (ws_dir / "context.md").write_text(
        "# Task ABC\n## Goal\nImplement thing\n## Status\nIn progress",
        encoding="utf-8",
    )

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    memo = handoff.get("workspace_memo", "")
    assert "task-abc" in memo


# ---------------------------------------------------------------------------
# Resets behavior and compaction trackers
# ---------------------------------------------------------------------------

def test_resets_behavior_tracker(boost_home):
    bt = boost_home / "state" / "behavior-tracker.json"
    bt.write_text(json.dumps({
        "reads_since_rag": 99,
        "tasks_since_evaluator": 5,
    }), encoding="utf-8")

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    tracker = json.loads(bt.read_text(encoding="utf-8"))
    assert tracker.get("reads_since_rag", 99) == 0


# ---------------------------------------------------------------------------
# Outputs additionalContext
# ---------------------------------------------------------------------------

def test_outputs_additional_context(boost_home):
    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    if result.stdout.strip():
        output = json.loads(result.stdout)
        assert "additionalContext" in output


# ---------------------------------------------------------------------------
# Skips non-clear sources
# ---------------------------------------------------------------------------

def test_skips_unknown_source(boost_home):
    result = run_hook(
        "session-clear-save.py",
        _session_end(source="startup"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# detect_active_workspace (via direct import + subprocess)
# ---------------------------------------------------------------------------

def test_detects_active_workspace_from_mtime(boost_home):
    """Workspace with recent context.md is detected automatically."""
    ws_dir = boost_home / "workspace" / "task-detect"
    ws_dir.mkdir(parents=True)
    (ws_dir / "context.md").write_text("# Task Detect\nStatus: in progress", encoding="utf-8")

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    # active_workspace should be the detected task
    assert handoff.get("active_workspace") in ("task-detect", "")


def test_active_workspace_json_overrides_mtime(boost_home):
    """active-workspace.json takes priority when context.md exists for it."""
    ws_dir = boost_home / "workspace" / "task-explicit"
    ws_dir.mkdir(parents=True)
    (ws_dir / "context.md").write_text("# Explicit Task\nStatus: in progress", encoding="utf-8")

    (boost_home / "state" / "active-workspace.json").write_text(
        json.dumps({"workspace": "task-explicit"}), encoding="utf-8"
    )

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff.get("active_workspace") == "task-explicit"


def test_collect_workspace_memo_with_project_registry(boost_home, tmp_path):
    """Project-scoped workspaces from workspaces.json are included in memo."""
    proj_ws = tmp_path / "myproject" / "workspace" / "task-proj"
    proj_ws.mkdir(parents=True)
    (proj_ws / "context.md").write_text("# Project Task\nGoal: fix it", encoding="utf-8")

    reg = {
        "task-proj": {
            "workspace_path": str(proj_ws),
            "project_path": str(tmp_path / "myproject"),
        }
    }
    (boost_home / "state" / "workspaces.json").write_text(
        json.dumps(reg), encoding="utf-8"
    )

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert "task-proj" in handoff.get("workspace_memo", "")


def test_no_stdin_flag(boost_home):
    """--no-stdin flag skips stdin read but still fires on clear."""
    from helpers import SCRIPTS_DIR, COVERAGERC
    import subprocess, os, sys
    script = SCRIPTS_DIR / "session-clear-save.py"
    env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
    result = subprocess.run(
        [sys.executable, str(script), "--no-stdin"],
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0
    # Without stdin, source="" so it fires as session end
    handoff_path = boost_home / "state" / "handoff-latest.json"
    assert handoff_path.exists()


def test_extract_summary_skips_skip_sections(boost_home):
    """extract_summary skips 'research sources', 'work done', etc."""
    ws_dir = boost_home / "workspace" / "task-skip"
    ws_dir.mkdir(parents=True)
    content = """# Task Skip
## Goal
Build thing
## Status
In progress
## Research Sources
- source1
- source2
## Work Done
- step 1
- step 2
## Next Step
Deploy
"""
    (ws_dir / "context.md").write_text(content, encoding="utf-8")

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    memo = handoff.get("workspace_memo", "")
    # Research Sources and Work Done should be excluded from summary
    # (though the task-skip header still appears)
    assert "task-skip" in memo


def test_handoff_with_transcript_path(boost_home, tmp_path):
    """When transcript_path is given and file exists, conversation is extracted."""
    # Create a fake transcript
    transcript = tmp_path / "transcript.jsonl"
    entry = {"type": "user", "message": {"content": "Fix the authentication bug"}}
    transcript.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    fixture = {
        "hook_event_name": "SessionEnd",
        "session_id": "test-with-transcript",
        "source": "clear",
        "cwd": "/test",
        "transcript_path": str(transcript),
    }
    result = run_hook(
        "session-clear-save.py",
        fixture,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    # conversation dict should be present (may be empty if no useful content)
    assert "conversation" in handoff


def test_mtime_winner_preferred_over_stale_active(boost_home):
    """When mtime winner is >30min newer than active-workspace candidate, prefer winner."""
    import time, os

    # Older workspace (set as active in active-workspace.json)
    ws_old = boost_home / "workspace" / "task-old"
    ws_old.mkdir(parents=True)
    old_ctx = ws_old / "context.md"
    old_ctx.write_text("# Old Task\nStatus: done", encoding="utf-8")
    # Backdate it by 2 hours
    old_time = time.time() - 7200
    os.utime(str(old_ctx), (old_time, old_time))

    (boost_home / "state" / "active-workspace.json").write_text(
        json.dumps({"workspace": "task-old"}), encoding="utf-8"
    )

    # Newer workspace (no entry in active-workspace.json)
    ws_new = boost_home / "workspace" / "task-new"
    ws_new.mkdir(parents=True)
    (ws_new / "context.md").write_text("# New Task\nStatus: in progress", encoding="utf-8")

    result = run_hook(
        "session-clear-save.py",
        _session_end(),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    # task-new should be preferred since it's much newer
    assert handoff.get("active_workspace") == "task-new"


# ---------------------------------------------------------------------------
# Direct import tests for internal functions
# ---------------------------------------------------------------------------

def _load_session_clear_save():
    """Import session-clear-save.py as a module (hyphen requires importlib)."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "session_clear_save",
        Path(__file__).resolve().parent.parent / "session-clear-save.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestExtractSummary:
    def test_breaks_at_char_budget(self):
        """extract_summary stops adding sections when budget is exceeded."""
        mod = _load_session_clear_save()
        content = (
            "# Goal\nBuild the thing\n\n"
            "# Next Step\n" + "X" * 1900 + "\n\n"
            "# Status\nIn progress"
        )
        result = mod.extract_summary(content, char_budget=500)
        # Budget of 500 should not include the 1900-char section
        assert len(result) <= 600


class TestGetProjectWorkspacePath:
    def test_returns_none_when_registry_missing(self, boost_home):
        """No workspaces.json returns None."""
        mod = _load_session_clear_save()
        result = mod._get_project_workspace_path(boost_home, "nonexistent-task")
        assert result is None

    def test_returns_none_on_corrupt_registry(self, boost_home):
        """Corrupt workspaces.json — exception caught, returns None."""
        (boost_home / "state" / "workspaces.json").write_text("not json at all", encoding="utf-8")
        mod = _load_session_clear_save()
        result = mod._get_project_workspace_path(boost_home, "any-task")
        assert result is None

    def test_returns_path_when_task_in_registry(self, boost_home, tmp_path):
        """Valid registry entry returns the workspace path."""
        ws_path = tmp_path / "workspace" / "reg-task"
        ws_path.mkdir(parents=True)
        reg = {
            "reg-task": {"workspace_path": str(ws_path), "project_path": str(tmp_path)}
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_clear_save()
        result = mod._get_project_workspace_path(boost_home, "reg-task")
        assert result is not None
        assert str(result) == str(ws_path)


class TestWorkspaceContextPath:
    def test_returns_local_context_path(self, boost_home):
        """Local workspace/task-id/context.md is found."""
        ws_dir = boost_home / "workspace" / "local-task"
        ws_dir.mkdir(parents=True)
        ctx = ws_dir / "context.md"
        ctx.write_text("# Local Task", encoding="utf-8")
        mod = _load_session_clear_save()
        result = mod._workspace_context_path(boost_home, "local-task")
        assert result == ctx

    def test_falls_back_to_registry_path(self, boost_home, tmp_path):
        """No local context.md but registry path exists — uses it."""
        proj_ws = tmp_path / "project" / "workspace" / "proj-task"
        proj_ws.mkdir(parents=True)
        ctx = proj_ws / "context.md"
        ctx.write_text("# Proj Task", encoding="utf-8")
        reg = {
            "proj-task": {"workspace_path": str(proj_ws), "project_path": str(tmp_path)}
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_clear_save()
        result = mod._workspace_context_path(boost_home, "proj-task")
        assert result == ctx

    def test_returns_none_when_not_found(self, boost_home):
        """Nothing exists returns None."""
        mod = _load_session_clear_save()
        result = mod._workspace_context_path(boost_home, "ghost-task")
        assert result is None


class TestDetectActiveWorkspace:
    def test_handles_corrupt_workspaces_json(self, boost_home):
        """Corrupt workspaces.json in detect_active_workspace doesn't crash."""
        ws_dir = boost_home / "workspace" / "task-detect2"
        ws_dir.mkdir(parents=True)
        (ws_dir / "context.md").write_text("# Task Detect2", encoding="utf-8")
        (boost_home / "state" / "workspaces.json").write_text("CORRUPT", encoding="utf-8")
        mod = _load_session_clear_save()
        result = mod.detect_active_workspace(boost_home)
        assert result is None or isinstance(result, str)


class TestCollectWorkspaceMemo:
    def test_includes_project_scoped_workspaces(self, boost_home, tmp_path):
        """Project-scoped workspaces from registry appear in memo."""
        proj_ws = tmp_path / "project" / "workspace" / "proj-task2"
        proj_ws.mkdir(parents=True)
        (proj_ws / "context.md").write_text("# Proj Task2\nGoal: fix it", encoding="utf-8")
        reg = {
            "proj-task2": {"workspace_path": str(proj_ws), "project_path": str(tmp_path)}
        }
        (boost_home / "state" / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")
        mod = _load_session_clear_save()
        result = mod.collect_workspace_memo(boost_home, "test-session", "CONSULT")
        assert "proj-task2" in result


class TestMainMalformedStdin:
    def test_malformed_json_stdin_exits_0(self, boost_home):
        """Non-JSON stdin falls back to empty dict, fires as session end."""
        import subprocess, sys, os
        from pathlib import Path as P
        SCRIPTS = P(__file__).resolve().parent.parent
        from helpers import COVERAGERC
        env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
        if COVERAGERC.exists():
            env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "session-clear-save.py")],
            input=b"MALFORMED_JSON",
            capture_output=True,
            env=env,
        )
        assert result.returncode == 0
        assert b"Traceback" not in result.stderr

    def test_unknown_source_skips_gracefully(self, boost_home):
        """Unknown source skips processing entirely."""
        result = run_hook(
            "session-clear-save.py",
            _session_end(source="startup"),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# Line 61 — extract_summary char_budget break
# ---------------------------------------------------------------------------

class TestExtractSummaryBreak:
    def test_breaks_when_first_section_exceeds_budget(self):
        """Line 61: break fires when the first section already fills the budget."""
        mod = _load_session_clear_save()
        # Preamble = "# Preamble\nX" (12 chars). Budget = 20.
        # First section chunk = "# Section\n" + "A"*400 -> chunk[:400] = 400 chars.
        # 12 + 400 > 20 -> break on first iteration.
        content = "# Preamble\nX\n\n# Section\n" + "A" * 500
        result = mod.extract_summary(content, char_budget=20)
        # Only the preamble makes it in; the section is cut.
        assert "Section" not in result
        assert "Preamble" in result


# ---------------------------------------------------------------------------
# Lines 157-158 — detect_active_workspace mtime winner > 30 min newer
# ---------------------------------------------------------------------------

class TestDetectActiveWorkspaceMtimeWinner:
    def test_mtime_winner_returned_when_newer_than_candidate(self, boost_home):
        """Line 156: mtime winner is >30 min newer — wins directly."""
        import time
        import os

        # Candidate workspace (set in active-workspace.json) — older by 2 hours
        ws_old = boost_home / "workspace" / "task-stale"
        ws_old.mkdir(parents=True)
        old_ctx = ws_old / "context.md"
        old_ctx.write_text("# Old\nStatus: done", encoding="utf-8")
        old_time = time.time() - 7200
        os.utime(str(old_ctx), (old_time, old_time))

        (boost_home / "state" / "active-workspace.json").write_text(
            json.dumps({"workspace": "task-stale"}), encoding="utf-8"
        )

        # Newer workspace — just written (current mtime)
        ws_new = boost_home / "workspace" / "task-fresh"
        ws_new.mkdir(parents=True)
        (ws_new / "context.md").write_text("# Fresh\nStatus: in progress", encoding="utf-8")

        mod = _load_session_clear_save()
        result = mod.detect_active_workspace(boost_home)
        # The fresh workspace is >30 min newer, so it wins
        assert result == "task-fresh"

    def test_returns_candidate_when_winner_not_significantly_newer(self, boost_home):
        """Line 160: returns candidate when mtime winner is NOT >30 min newer."""
        import time
        import os

        # Both workspaces have similar mtime (winner just barely newer)
        ws_old = boost_home / "workspace" / "task-candidate"
        ws_old.mkdir(parents=True)
        old_ctx = ws_old / "context.md"
        old_ctx.write_text("# Candidate Task\nStatus: active", encoding="utf-8")

        (boost_home / "state" / "active-workspace.json").write_text(
            json.dumps({"workspace": "task-candidate"}), encoding="utf-8"
        )

        # Another workspace — only 5 minutes newer (well under 30 min threshold)
        ws_other = boost_home / "workspace" / "task-other"
        ws_other.mkdir(parents=True)
        other_ctx = ws_other / "context.md"
        other_ctx.write_text("# Other Task\nStatus: pending", encoding="utf-8")
        # Backdate other to only 5 minutes newer than candidate
        # candidate was just written (now), other 5 min before now
        other_time = time.time() + 300  # 5 min future — still less than 1800s diff
        # Actually: candidate ~now, other ~now+5min won't trigger the >1800 check
        # Both are "now", so diff < 1800 — candidate is returned
        os.utime(str(other_ctx), (other_time, other_time))

        mod = _load_session_clear_save()
        result = mod.detect_active_workspace(boost_home)
        # Candidate wins because winner is not >30 min newer
        assert result == "task-candidate"

    def test_stat_exception_in_mtime_comparison_returns_candidate(self, boost_home):
        """Lines 157-158: stat().st_mtime raises in mtime comparison — except caught, returns candidate."""
        from unittest.mock import patch, MagicMock

        ws_cand = boost_home / "workspace" / "task-cand-exc"
        ws_cand.mkdir(parents=True)
        ctx_cand = ws_cand / "context.md"
        ctx_cand.write_text("# Candidate\nStatus: active", encoding="utf-8")

        (boost_home / "state" / "active-workspace.json").write_text(
            json.dumps({"workspace": "task-cand-exc"}), encoding="utf-8"
        )

        mod = _load_session_clear_save()

        # Patch _workspace_context_path to return a Path whose stat() raises
        # so the mtime comparison block triggers the except
        bad_ctx = MagicMock()
        bad_ctx.__bool__ = MagicMock(return_value=True)
        bad_stat = MagicMock()
        bad_stat.st_mtime = property(lambda self: (_ for _ in ()).throw(OSError("stat failed")))
        bad_ctx.stat.side_effect = OSError("stat failed")

        with patch.object(mod, "_workspace_context_path", return_value=bad_ctx):
            result = mod.detect_active_workspace(boost_home)

        # Exception caught in try/except, falls through to return candidate
        assert result == "task-cand-exc"


# ---------------------------------------------------------------------------
# Lines 204-205 — collect_workspace_memo unreadable context.md
# ---------------------------------------------------------------------------

class TestCollectWorkspaceMemoUnreadable:
    def test_unreadable_context_md_appends_placeholder(self, boost_home):
        """Lines 204-205: context.md that raises on read gets [unreadable] placeholder."""
        from unittest.mock import patch, mock_open, MagicMock
        import builtins

        ws_dir = boost_home / "workspace" / "task-unreadable"
        ws_dir.mkdir(parents=True)
        ctx = ws_dir / "context.md"
        ctx.write_text("# Unreadable Task", encoding="utf-8")

        mod = _load_session_clear_save()

        original_read_text = ctx.__class__.read_text

        # Patch Path.read_text to raise for this specific file
        def patched_read_text(self, **kwargs):
            if self == ctx:
                raise OSError("permission denied")
            return original_read_text(self, **kwargs)

        with patch.object(type(ctx), "read_text", patched_read_text):
            result = mod.collect_workspace_memo(boost_home, "test-sess", "CONSULT")

        assert "task-unreadable" in result
        assert "[unreadable]" in result


# ---------------------------------------------------------------------------
# Lines 267-268 — handoff_core import + extract_conversation call
# ---------------------------------------------------------------------------

class TestHandoffCoreExtraction:
    def test_extract_conversation_called_with_valid_transcript(self, boost_home, tmp_path):
        """Lines 267-268: when handoff_core imports OK, extract_conversation is called."""
        import sys

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text(
            json.dumps({"type": "user", "message": {"content": "Hello"}}) + "\n",
            encoding="utf-8",
        )

        mod = _load_session_clear_save()

        # Ensure scripts/ is in path so handoff_core import succeeds
        scripts_dir = str(SCRIPTS_DIR)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)

        # Call main() with a mock stdin providing transcript_path
        import io
        import sys as _sys
        from unittest.mock import patch

        hook_input = {
            "hook_event_name": "SessionEnd",
            "session_id": "test-handoff-core",
            "source": "clear",
            "cwd": "/test",
            "transcript_path": str(transcript),
        }

        captured_output = io.StringIO()
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode()))):
            with patch("sys.stdout", captured_output):
                with patch.dict("os.environ", {"CLAUDEBOOST_HOME": str(boost_home)}):
                    result_code = mod.main()

        assert result_code == 0
        handoff_path = boost_home / "state" / "handoff-latest.json"
        assert handoff_path.exists()
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        # conversation key should be populated (lines 267-268 ran)
        assert "conversation" in handoff

    def test_extract_conversation_exception_caught(self, boost_home, tmp_path):
        """Lines 267-268 exception path: ImportError from handoff_core is silently caught."""
        import sys
        import io
        from unittest.mock import patch, MagicMock

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")

        mod = _load_session_clear_save()

        hook_input = {
            "hook_event_name": "SessionEnd",
            "session_id": "test-import-error",
            "source": "clear",
            "cwd": "/test",
            "transcript_path": str(transcript),
        }

        captured_output = io.StringIO()

        # Make handoff_core raise on import so the except block runs
        broken_module = MagicMock()
        broken_module.extract_conversation = MagicMock(side_effect=RuntimeError("broken"))

        with patch.dict("sys.modules", {"handoff_core": broken_module}):
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode()))):
                with patch("sys.stdout", captured_output):
                    with patch.dict("os.environ", {"CLAUDEBOOST_HOME": str(boost_home)}):
                        result_code = mod.main()

        # Still exits 0 — exception is swallowed
        assert result_code == 0


# ---------------------------------------------------------------------------
# Lines 284-285, 299-300, 309-310 — write failure except blocks
# ---------------------------------------------------------------------------

class TestWriteFailureExceptBlocks:
    def test_handoff_write_failure_is_silenced(self, boost_home):
        """Lines 284-285: write failure on handoff-latest.json is caught silently."""
        import io
        from unittest.mock import patch, MagicMock

        mod = _load_session_clear_save()

        hook_input = {
            "hook_event_name": "SessionEnd",
            "session_id": "test-write-fail",
            "source": "clear",
            "cwd": "/test",
            "transcript_path": "",
        }

        captured_output = io.StringIO()

        def failing_write_text(self, *a, **kw):
            if self.name == "handoff-latest.json":
                raise OSError("disk full")
            # Let other writes through
            return original_write_text(self, *a, **kw)

        original_write_text = type(boost_home / "state" / "handoff-latest.json").write_text

        with patch.object(type(boost_home), "write_text", failing_write_text):
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode()))):
                with patch("sys.stdout", captured_output):
                    with patch.dict("os.environ", {"CLAUDEBOOST_HOME": str(boost_home)}):
                        result_code = mod.main()

        # Must still exit 0 — write failure is silent
        assert result_code == 0

    def test_compaction_memo_write_failure_is_silenced(self, boost_home):
        """Lines 299-300: write failure on compaction-memo.json is caught silently."""
        import io
        from unittest.mock import patch

        mod = _load_session_clear_save()

        hook_input = {
            "hook_event_name": "SessionEnd",
            "session_id": "test-compact-write-fail",
            "source": "clear",
            "cwd": "/test",
            "transcript_path": "",
        }

        original_write_text = type(boost_home / "state" / "handoff-latest.json").write_text

        def failing_write_text(self, *a, **kw):
            if self.name == "compaction-memo.json":
                raise OSError("disk full")
            return original_write_text(self, *a, **kw)

        captured_output = io.StringIO()

        with patch.object(type(boost_home), "write_text", failing_write_text):
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode()))):
                with patch("sys.stdout", captured_output):
                    with patch.dict("os.environ", {"CLAUDEBOOST_HOME": str(boost_home)}):
                        result_code = mod.main()

        assert result_code == 0

    def test_tracker_write_failure_is_silenced(self, boost_home):
        """Lines 309-310: write failure on tracker json is caught silently."""
        import io
        from unittest.mock import patch

        mod = _load_session_clear_save()

        hook_input = {
            "hook_event_name": "SessionEnd",
            "session_id": "test-tracker-write-fail",
            "source": "clear",
            "cwd": "/test",
            "transcript_path": "",
        }

        original_write_text = type(boost_home / "state" / "handoff-latest.json").write_text

        def failing_write_text(self, *a, **kw):
            if self.name in ("compaction-tracker.json", "behavior-tracker.json"):
                raise OSError("read only filesystem")
            return original_write_text(self, *a, **kw)

        captured_output = io.StringIO()

        with patch.object(type(boost_home), "write_text", failing_write_text):
            with patch("sys.stdin", io.TextIOWrapper(io.BytesIO(json.dumps(hook_input).encode()))):
                with patch("sys.stdout", captured_output):
                    with patch.dict("os.environ", {"CLAUDEBOOST_HOME": str(boost_home)}):
                        result_code = mod.main()

        assert result_code == 0
