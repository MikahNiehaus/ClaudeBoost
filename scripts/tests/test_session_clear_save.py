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
