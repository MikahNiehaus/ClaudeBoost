"""
Tests for scripts/compaction-primer.py (PreCompact hook).

Injects 5 standing orders before compaction. Always exits 0.
"""
from __future__ import annotations

import json
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _precompact() -> dict:
    return {"hook_event_name": "PreCompact", "session_id": "test"}


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0():
    result = run_hook("compaction-primer.py", _precompact())
    assert result.returncode == 0


def test_exits_0_on_empty_input():
    result = run_hook("compaction-primer.py", {})
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Outputs additionalContext with standing orders
# ---------------------------------------------------------------------------

def test_outputs_standing_orders():
    result = run_hook("compaction-primer.py", _precompact())
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert "additionalContext" in output
    ctx = output["additionalContext"]
    assert "STANDING ORDERS" in ctx


def test_standing_orders_mention_rag():
    result = run_hook("compaction-primer.py", _precompact())
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]
    assert "RAG" in ctx or "http://127.0.0.1:8612" in ctx


def test_standing_orders_mention_evaluator():
    result = run_hook("compaction-primer.py", _precompact())
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]
    assert "evaluator" in ctx


def test_standing_orders_mention_consult():
    result = run_hook("compaction-primer.py", _precompact())
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]
    assert "CONSULT" in ctx


def test_no_stderr_output():
    result = run_hook("compaction-primer.py", _precompact())
    assert result.returncode == 0
    assert result.stderr == b""
