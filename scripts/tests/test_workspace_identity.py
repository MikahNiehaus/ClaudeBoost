"""
Tests for scripts/workspace_identity.py — shared workspace identity module.

Covers: get_boost_home, normalize_cwd, get_instance_id,
        read_ws_instance, write_ws_instance, resolve_active_workspace.
"""
from __future__ import annotations

import json
import os
import sys
import pytest
from pathlib import Path

# Add scripts/ to sys.path so we can import the module under test
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# get_boost_home
# ---------------------------------------------------------------------------

class TestGetBoostHome:
    def test_from_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLAUDEBOOST_HOME", str(tmp_path))
        from workspace_identity import get_boost_home
        assert get_boost_home() == tmp_path

    def test_fallback_to_script_parent(self, monkeypatch):
        monkeypatch.delenv("CLAUDEBOOST_HOME", raising=False)
        from workspace_identity import get_boost_home
        result = get_boost_home()
        # Should be two levels up from workspace_identity.py (scripts/ -> repo root)
        assert result.is_dir()


# ---------------------------------------------------------------------------
# normalize_cwd
# ---------------------------------------------------------------------------

class TestNormalizeCwd:
    def test_backslashes_to_forward(self):
        from workspace_identity import normalize_cwd
        assert normalize_cwd("C:\\Users\\test\\project") == "C:/Users/test/project"

    def test_trailing_slash_stripped(self):
        from workspace_identity import normalize_cwd
        assert normalize_cwd("C:/Users/test/project/") == "C:/Users/test/project"

    def test_already_normalized(self):
        from workspace_identity import normalize_cwd
        assert normalize_cwd("C:/Users/test") == "C:/Users/test"


# ---------------------------------------------------------------------------
# get_instance_id
# ---------------------------------------------------------------------------

class TestGetInstanceId:
    def test_session_id_highest_priority(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc123")
        monkeypatch.setenv("CLAUDEBOOST_INSTANCE_ID", "should-not-use")
        from workspace_identity import get_instance_id
        assert get_instance_id() == "session-abc123"

    def test_env_instance_id_fallback(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.setenv("CLAUDEBOOST_INSTANCE_ID", "custom-id")
        # Patch _find_claude_pid_windows to return None (skip Windows walk)
        import workspace_identity
        monkeypatch.setattr(workspace_identity, "_find_claude_pid_windows", lambda: None)
        assert workspace_identity.get_instance_id() == "custom-id"

    def test_ppid_last_resort(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.delenv("CLAUDEBOOST_INSTANCE_ID", raising=False)
        import workspace_identity
        monkeypatch.setattr(workspace_identity, "_find_claude_pid_windows", lambda: None)
        result = workspace_identity.get_instance_id()
        assert result.startswith("ppid-")

    def test_node_pid_second_priority(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        import workspace_identity
        monkeypatch.setattr(workspace_identity, "_find_claude_pid_windows", lambda: 12345)
        assert workspace_identity.get_instance_id() == "node-12345"


# ---------------------------------------------------------------------------
# read_ws_instance
# ---------------------------------------------------------------------------

class TestReadWsInstance:
    def test_new_format_exact_match(self, tmp_path):
        from workspace_identity import read_ws_instance
        inst = tmp_path / "inst.json"
        inst.write_text(json.dumps({"C:/Dev/Project": "task-1"}), encoding="utf-8")
        assert read_ws_instance(inst, "C:/Dev/Project") == "task-1"

    def test_new_format_case_insensitive(self, tmp_path):
        from workspace_identity import read_ws_instance
        inst = tmp_path / "inst.json"
        inst.write_text(json.dumps({"C:/Dev/Project": "task-1"}), encoding="utf-8")
        assert read_ws_instance(inst, "c:/dev/project") == "task-1"

    def test_old_format_matching_cwd(self, tmp_path):
        from workspace_identity import read_ws_instance
        inst = tmp_path / "inst.json"
        inst.write_text(json.dumps({
            "workspace_id": "old-task",
            "cwd": "C:/Dev/Project"
        }), encoding="utf-8")
        assert read_ws_instance(inst, "C:/Dev/Project") == "old-task"

    def test_old_format_different_cwd(self, tmp_path):
        from workspace_identity import read_ws_instance
        inst = tmp_path / "inst.json"
        inst.write_text(json.dumps({
            "workspace_id": "old-task",
            "cwd": "C:/Other/Path"
        }), encoding="utf-8")
        assert read_ws_instance(inst, "C:/Dev/Project") == ""

    def test_missing_file(self, tmp_path):
        from workspace_identity import read_ws_instance
        assert read_ws_instance(tmp_path / "nope.json", "C:/Dev") == ""

    def test_backslash_normalization(self, tmp_path):
        from workspace_identity import read_ws_instance
        inst = tmp_path / "inst.json"
        inst.write_text(json.dumps({"C:\\Dev\\Project": "task-bs"}), encoding="utf-8")
        assert read_ws_instance(inst, "C:/Dev/Project") == "task-bs"


# ---------------------------------------------------------------------------
# write_ws_instance
# ---------------------------------------------------------------------------

class TestWriteWsInstance:
    def test_new_file(self, tmp_path):
        from workspace_identity import write_ws_instance
        ws_dir = tmp_path / "ws-instance"
        ws_dir.mkdir()
        write_ws_instance(tmp_path, "test-inst", "C:/Dev/Proj", "task-new")
        data = json.loads((ws_dir / "test-inst.json").read_text(encoding="utf-8"))
        assert data["C:/Dev/Proj"] == "task-new"

    def test_update_existing(self, tmp_path):
        from workspace_identity import write_ws_instance
        ws_dir = tmp_path / "ws-instance"
        ws_dir.mkdir()
        existing = {"C:/Other": "task-other"}
        (ws_dir / "inst-1.json").write_text(json.dumps(existing), encoding="utf-8")
        write_ws_instance(tmp_path, "inst-1", "C:/Dev/Proj", "task-2")
        data = json.loads((ws_dir / "inst-1.json").read_text(encoding="utf-8"))
        assert data["C:/Dev/Proj"] == "task-2"
        assert data["C:/Other"] == "task-other"

    def test_clear_workspace(self, tmp_path):
        from workspace_identity import write_ws_instance
        ws_dir = tmp_path / "ws-instance"
        ws_dir.mkdir()
        existing = {"C:/Dev": "task-1", "C:/Other": "task-2"}
        (ws_dir / "inst-x.json").write_text(json.dumps(existing), encoding="utf-8")
        write_ws_instance(tmp_path, "inst-x", "C:/Dev", "")
        data = json.loads((ws_dir / "inst-x.json").read_text(encoding="utf-8"))
        assert "C:/Dev" not in data
        assert data["C:/Other"] == "task-2"

    def test_migrate_old_format(self, tmp_path):
        from workspace_identity import write_ws_instance
        ws_dir = tmp_path / "ws-instance"
        ws_dir.mkdir()
        old = {"workspace_id": "old-ws", "cwd": "C:/Old/Path"}
        (ws_dir / "migr.json").write_text(json.dumps(old), encoding="utf-8")
        write_ws_instance(tmp_path, "migr", "C:/New/Path", "new-ws")
        data = json.loads((ws_dir / "migr.json").read_text(encoding="utf-8"))
        # Old format keys should be gone
        assert "workspace_id" not in data
        assert "cwd" not in data
        # New format: both old CWD (migrated) and new CWD
        assert data.get("C:/Old/Path") == "old-ws"
        assert data["C:/New/Path"] == "new-ws"


# ---------------------------------------------------------------------------
# resolve_active_workspace
# ---------------------------------------------------------------------------

class TestResolveActiveWorkspace:
    def test_from_instance_file(self, tmp_path, monkeypatch):
        from workspace_identity import resolve_active_workspace
        ws_dir = tmp_path / "ws-instance"
        ws_dir.mkdir(parents=True)
        cwd = "C:/Dev/MyProject"
        (ws_dir / "session-test123.json").write_text(
            json.dumps({cwd: "task-from-inst"}), encoding="utf-8"
        )
        import workspace_identity
        monkeypatch.setattr(workspace_identity, "get_instance_id", lambda: "session-test123")
        result = resolve_active_workspace(tmp_path, cwd)
        assert result == "task-from-inst"

    def test_scan_fallback(self, tmp_path, monkeypatch):
        from workspace_identity import resolve_active_workspace
        ws_dir = tmp_path / "ws-instance"
        ws_dir.mkdir(parents=True)
        cwd = "C:/Dev/MyProject"
        # Write to a different instance file (not ours)
        (ws_dir / "session-other.json").write_text(
            json.dumps({cwd: "task-scanned"}), encoding="utf-8"
        )
        import workspace_identity
        # Our instance file doesn't exist
        monkeypatch.setattr(workspace_identity, "get_instance_id", lambda: "session-missing")
        result = resolve_active_workspace(tmp_path, cwd)
        assert result == "task-scanned"

    def test_active_workspace_json_fallback(self, tmp_path, monkeypatch):
        from workspace_identity import resolve_active_workspace
        import workspace_identity
        monkeypatch.setattr(workspace_identity, "get_instance_id", lambda: "session-none")
        # No ws-instance files, but active-workspace.json exists
        (tmp_path / "active-workspace.json").write_text(
            json.dumps({"workspace": "task-from-aw"}), encoding="utf-8"
        )
        result = resolve_active_workspace(tmp_path, "C:/Dev/MyProject")
        assert result == "task-from-aw"

    def test_empty_when_nothing(self, tmp_path, monkeypatch):
        from workspace_identity import resolve_active_workspace
        import workspace_identity
        monkeypatch.setattr(workspace_identity, "get_instance_id", lambda: "session-none")
        result = resolve_active_workspace(tmp_path, "C:/Dev/Empty")
        assert result == ""
