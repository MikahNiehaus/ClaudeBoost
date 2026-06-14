"""
Tests for scripts/workspace-boost-gate.py (PreToolUse/Bash hook).

Blocks workspace mkdir when /boost sentinel is absent.
"""
from __future__ import annotations

import pytest
from helpers import SCRIPTS_DIR, run_hook, pretooluse


def _mkdir_workspace(path: str = "/tmp/workspace/task-1") -> dict:
    return pretooluse("Bash", {"command": f"mkdir -p {path}"})


# ---------------------------------------------------------------------------
# Sentinel present: pass
# ---------------------------------------------------------------------------

def test_passes_when_sentinel_exists(tmp_path):
    sentinel = tmp_path / "claudeboost_rag_ok"
    sentinel.touch()

    result = run_hook(
        "workspace-boost-gate.py",
        _mkdir_workspace(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Sentinel absent: block
# ---------------------------------------------------------------------------

def test_blocks_when_sentinel_missing(tmp_path):
    # tmp_path is empty — no sentinel
    result = run_hook(
        "workspace-boost-gate.py",
        _mkdir_workspace(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 2
    assert b"BLOCKED" in result.stderr
    assert b"/boost" in result.stderr


def test_block_message_mentions_rag(tmp_path):
    result = run_hook(
        "workspace-boost-gate.py",
        _mkdir_workspace(),
        env_overrides={"TEMP": str(tmp_path)},
    )
    assert result.returncode == 2
    assert b"RAG" in result.stderr


# ---------------------------------------------------------------------------
# Edge case: empty stdin
# ---------------------------------------------------------------------------

def test_blocks_on_empty_input_when_no_sentinel(tmp_path):
    import subprocess, sys, os
    script = SCRIPTS_DIR / "workspace-boost-gate.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input=b"{}",
        capture_output=True,
        env={**os.environ, "TEMP": str(tmp_path)},
    )
    assert result.returncode == 2
