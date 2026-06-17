"""
Tests for scripts/telemetry-session.py (SessionStart / SessionEnd hook).

Covers:
- SessionStart creates session.json with a resolved session_id
- SessionStart early-return patches session_id from "unknown" when session is still active
- SessionStart early-return stamps last_resumed_at
- SessionEnd writes ended_at
- SessionEnd recomputes rag_count from rag-usage.jsonl (fixes off-by-one race)
- DISABLE_TELEMETRY=1 silences all writes
"""
from __future__ import annotations

import json
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "telemetry_session",
        SCRIPTS_DIR / "telemetry-session.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_workspace(tmp_path: Path, boost_home: Path) -> Path:
    """Create a workspace dir and wire up active-workspace.json."""
    ws = tmp_path / "workspace" / "TFF-TEST"
    ws.mkdir(parents=True)
    (boost_home / "state").mkdir(parents=True, exist_ok=True)
    (boost_home / "state" / "active-workspace.json").write_text(
        json.dumps({
            "workspace": "TFF-TEST",
            "workspace_path": str(ws),
            "project_path": str(tmp_path),
        }),
        encoding="utf-8",
    )
    return ws


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_session_start_exits_0(tmp_path, boost_home):
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_session_end_exits_0(tmp_path, boost_home):
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# SessionStart — fresh session creation
# ---------------------------------------------------------------------------

def test_session_start_creates_session_json(tmp_path, boost_home):
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    session_file = ws / "Telemetry" / "session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text())
    assert data["workspace_id"] == "TFF-TEST"
    assert data["ended_at"] is None
    assert data["tool_count"] == 0
    assert data["rag_count"] == 0


def test_session_start_writes_valid_session_id(tmp_path, boost_home):
    """SessionStart generates a UUID and writes it to session-id.txt and session.json."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    sid_file = boost_home / "state" / "session-id.txt"
    assert sid_file.exists()
    sid = sid_file.read_text().strip()
    assert len(sid) == 36  # UUID4 format

    session_file = ws / "Telemetry" / "session.json"
    data = json.loads(session_file.read_text())
    assert data["session_id"] == sid


# ---------------------------------------------------------------------------
# SessionStart — early-return / resume path
# ---------------------------------------------------------------------------

def test_session_start_does_not_overwrite_active_session(tmp_path, boost_home):
    """If session.json exists with ended_at=null, session is NOT recreated (tool_count preserved)."""
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()
    existing = {
        "session_id": "existing-uuid",
        "workspace_id": "TFF-TEST",
        "project_path_hash": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None,
        "tool_count": 99,
        "rag_count": 42,
    }
    (tel_dir / "session.json").write_text(json.dumps(existing, indent=2))

    mod = _load_module()
    import unittest.mock as mock
    with mock.patch.dict("os.environ", {"CLAUDEBOOST_HOME": str(boost_home)}):
        mod.BOOST_HOME = Path(boost_home)
        mod.handle_session_start()

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["tool_count"] == 99
    assert data["rag_count"] == 42


def test_session_start_patches_unknown_session_id_on_resume(tmp_path, boost_home):
    """When active session has session_id='unknown', it's updated from session-id.txt."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    correct_uuid = "40e7abef-c976-4098-8f10-958432df1f8d"
    (boost_home / "state" / "session-id.txt").write_text(correct_uuid)

    existing = {
        "session_id": "unknown",
        "workspace_id": "TFF-TEST",
        "project_path_hash": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None,
        "tool_count": 10,
        "rag_count": 5,
    }
    (tel_dir / "session.json").write_text(json.dumps(existing, indent=2))

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["session_id"] == correct_uuid
    assert data["tool_count"] == 10  # preserved


def test_session_start_does_not_patch_valid_session_id(tmp_path, boost_home):
    """When active session already has a valid session_id, it is NOT overwritten."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    (boost_home / "state" / "session-id.txt").write_text("different-uuid-from-file")

    existing = {
        "session_id": "valid-existing-uuid",
        "workspace_id": "TFF-TEST",
        "project_path_hash": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None,
        "tool_count": 20,
        "rag_count": 8,
    }
    (tel_dir / "session.json").write_text(json.dumps(existing, indent=2))

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["session_id"] == "valid-existing-uuid"


def test_session_start_stamps_last_resumed_at(tmp_path, boost_home):
    """On resume, last_resumed_at is written so long-idle gaps are visible."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    existing = {
        "session_id": "some-uuid",
        "workspace_id": "TFF-TEST",
        "project_path_hash": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None,
        "tool_count": 5,
        "rag_count": 2,
    }
    (tel_dir / "session.json").write_text(json.dumps(existing, indent=2))

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert "last_resumed_at" in data
    assert data["last_resumed_at"]  # non-empty ISO timestamp


# ---------------------------------------------------------------------------
# SessionEnd — ended_at and rag_count recomputation
# ---------------------------------------------------------------------------

def test_session_end_writes_ended_at(tmp_path, boost_home):
    """SessionEnd sets ended_at to a non-null ISO timestamp."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    existing = {
        "session_id": "test-uuid",
        "workspace_id": "TFF-TEST",
        "project_path_hash": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None,
        "tool_count": 100,
        "rag_count": 10,
    }
    (tel_dir / "session.json").write_text(json.dumps(existing, indent=2))

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["ended_at"] is not None
    assert "T" in data["ended_at"]


def test_session_end_recomputes_rag_count_from_jsonl(tmp_path, boost_home):
    """SessionEnd recomputes rag_count by counting rag-usage.jsonl lines (fixes off-by-one)."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    existing = {
        "session_id": "test-uuid",
        "workspace_id": "TFF-TEST",
        "project_path_hash": None,
        "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None,
        "tool_count": 50,
        "rag_count": 7,  # off by one — JSONL has 8 lines
    }
    (tel_dir / "session.json").write_text(json.dumps(existing, indent=2))

    rag_log = tel_dir / "rag-usage.jsonl"
    lines = [json.dumps({"ts": f"2026-01-01T00:00:0{i}+00:00", "endpoint": "/status"}) for i in range(8)]
    rag_log.write_text("\n".join(lines) + "\n")

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["rag_count"] == 8  # recomputed from JSONL, not the stale counter


def test_session_end_rag_count_ignores_blank_lines(tmp_path, boost_home):
    """Blank lines in rag-usage.jsonl are not counted."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    (tel_dir / "session.json").write_text(json.dumps({
        "session_id": "test", "workspace_id": "TFF-TEST",
        "project_path_hash": None, "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None, "tool_count": 10, "rag_count": 0,
    }, indent=2))

    rag_log = tel_dir / "rag-usage.jsonl"
    rag_log.write_text(
        '{"endpoint":"/status"}\n\n{"endpoint":"/context"}\n\n{"endpoint":"/search"}\n'
    )

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["rag_count"] == 3  # 3 non-blank lines


def test_session_end_rag_count_falls_back_when_no_jsonl(tmp_path, boost_home):
    """If rag-usage.jsonl doesn't exist, existing rag_count is kept."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    (tel_dir / "session.json").write_text(json.dumps({
        "session_id": "test", "workspace_id": "TFF-TEST",
        "project_path_hash": None, "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None, "tool_count": 10, "rag_count": 15,
    }, indent=2))

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0

    data = json.loads((tel_dir / "session.json").read_text())
    assert data["rag_count"] == 15  # unchanged — no JSONL to recompute from


def test_session_end_noop_when_no_session_file(tmp_path, boost_home):
    """SessionEnd silently does nothing if session.json doesn't exist."""
    from helpers import run_hook
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()

    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr


# ---------------------------------------------------------------------------
# DISABLE_TELEMETRY=1
# ---------------------------------------------------------------------------

def test_disable_telemetry_skips_session_start(tmp_path, boost_home):
    """DISABLE_TELEMETRY=1 prevents session.json from being created."""
    ws = _make_workspace(tmp_path, boost_home)
    from helpers import run_hook
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionStart"},
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "DISABLE_TELEMETRY": "1",
        },
    )
    assert result.returncode == 0
    assert not (ws / "Telemetry" / "session.json").exists()


def test_disable_telemetry_skips_session_end(tmp_path, boost_home):
    """DISABLE_TELEMETRY=1 prevents ended_at from being written."""
    ws = _make_workspace(tmp_path, boost_home)
    tel_dir = ws / "Telemetry"
    tel_dir.mkdir()
    (tel_dir / "session.json").write_text(json.dumps({
        "session_id": "test", "workspace_id": "TFF-TEST",
        "project_path_hash": None, "started_at": "2026-01-01T00:00:00+00:00",
        "ended_at": None, "tool_count": 1, "rag_count": 0,
    }, indent=2))

    from helpers import run_hook
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "SessionEnd"},
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "DISABLE_TELEMETRY": "1",
        },
    )
    assert result.returncode == 0
    data = json.loads((tel_dir / "session.json").read_text())
    assert data["ended_at"] is None  # unchanged


# ---------------------------------------------------------------------------
# Unknown event — no-op
# ---------------------------------------------------------------------------

def test_unknown_event_is_ignored(tmp_path, boost_home):
    """Unrecognised hook_event_name does nothing and exits 0."""
    _make_workspace(tmp_path, boost_home)
    from helpers import run_hook
    result = run_hook(
        "telemetry-session.py",
        {"hook_event_name": "PreToolUse"},
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr
