"""
Tests for scripts/rag-read-guard.py (PreToolUse/Read+Grep hook).

Behavior under test:
  - Counter below threshold, RAG live    -> exit 0
  - Counter at threshold, RAG live       -> exit 2 with "BLOCKED" message
  - Counter at threshold, RAG not live   -> exit 0 (fail-open when RAG is down)
  - Exempted file suffix (.json)         -> exit 0 regardless of counter
  - Exempted path fragment (context.md)  -> exit 0 regardless of counter
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, run_hook, pretooluse


def _read_fixture(file_path: str) -> dict:
    return pretooluse("Read", {"file_path": file_path})


def _write_tracker(boost_home: Path, reads_since_rag: int) -> None:
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text(
        json.dumps({"reads_since_rag": reads_since_rag}),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_passes_below_threshold(boost_home, rag_live):
    """Counter below threshold should always pass."""
    _write_tracker(boost_home, 0)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_when_rag_not_live(boost_home, rag_dead):
    """Guard fails open — if RAG is down, reads are never blocked."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_dead},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------

def test_blocks_at_threshold(boost_home, rag_live):
    """Counter >= RAG_THRESHOLD (2) with live RAG should exit 2."""
    _write_tracker(boost_home, 2)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 2
    assert b"BLOCKED" in result.stderr


def test_blocks_well_above_threshold(boost_home, rag_live):
    """Counter well above threshold should also block."""
    _write_tracker(boost_home, 10)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/some_file.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 2


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------

def test_passes_exempted_json_suffix(boost_home, rag_live):
    """JSON files are always exempted — no RAG needed."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/state/approvals.json"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_exempted_context_md(boost_home, rag_live):
    """workspace/*/context.md is always exempted."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/test/project/workspace/my-task/context.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_md_file_in_workspace_path(boost_home, rag_live):
    """An .md file that lives inside workspace/ is exempted even without matching name fragments."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/workspace/task-123/notes.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_blocks_md_file_outside_workspace(boost_home, rag_live):
    """.md file outside workspace/ is NOT exempted — goes through counter check."""
    _write_tracker(boost_home, 99)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/docs/design.md"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 2


def test_passes_glob_with_workspace_pattern(boost_home, rag_live):
    """Glob tool with workspace in pattern is exempted."""
    _write_tracker(boost_home, 99)
    fixture = {
        **pretooluse("Glob", {"pattern": "workspace/**/*.md"}),
    }
    result = run_hook(
        "rag-read-guard.py",
        fixture,
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_on_malformed_stdin(boost_home):
    """Malformed JSON on stdin — treated as empty payload, exemption falls through."""
    import subprocess, sys, os, json as _json
    from pathlib import Path as P
    SCRIPTS_DIR = P(__file__).resolve().parent.parent
    script = SCRIPTS_DIR / "rag-read-guard.py"
    env = {**os.environ, "CLAUDEBOOST_HOME": str(boost_home)}
    # Send raw non-JSON bytes as stdin
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b"THIS IS NOT JSON",
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0


def test_passes_with_malformed_tracker(boost_home, rag_live):
    """Malformed behavior-tracker.json defaults to reads_since_rag=0 → allow."""
    tracker = boost_home / "state" / "behavior-tracker.json"
    tracker.write_text("not json", encoding="utf-8")
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), **rag_live},
    )
    assert result.returncode == 0


def test_passes_plain_float_heartbeat(boost_home, tmp_path):
    """Plain float heartbeat (legacy format) — treated as live if fresh."""
    rag_index_dir = tmp_path / "rag-index"
    rag_index_dir.mkdir()
    import time
    (rag_index_dir / ".heartbeat").write_text(str(time.time()), encoding="utf-8")
    _write_tracker(boost_home, 0)
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "RAG_INDEX_DIR": str(rag_index_dir)},
    )
    assert result.returncode == 0


def test_passes_when_no_env_vars_set(boost_home):
    """Neither RAG_INDEX_DIR nor LOCALAPPDATA — uses Linux fallback, no heartbeat → fail-open."""
    result = run_hook(
        "rag-read-guard.py",
        _read_fixture("/project/src/main.py"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home), "RAG_INDEX_DIR": "", "LOCALAPPDATA": ""},
    )
    assert result.returncode == 0
