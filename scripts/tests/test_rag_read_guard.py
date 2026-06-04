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
