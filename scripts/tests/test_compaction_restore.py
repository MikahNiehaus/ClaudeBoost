"""
Tests for scripts/compaction-restore.py (SessionStart hook).

Injects saved handoff context after compaction or /clear. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


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
