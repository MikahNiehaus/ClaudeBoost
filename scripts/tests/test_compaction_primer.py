"""
Tests for scripts/compaction-primer.py (PreCompact hook).

Injects 5 standing orders before compaction. Always exits 0.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

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
    assert "http://127.0.0.1:8613/search" in ctx, ctx


def test_standing_orders_name_an_agent_that_exists():
    """The standing orders must name a verifier, and a real one.

    This used to assert only that the substring "evaluator" appeared. It
    passed for years while the text told every session to spawn
    `evaluator-agent`, which has never existed in this repo. Asserting a word
    rather than a resolvable agent is what let that survive, so the check is
    now against the agent directory itself.
    """
    result = run_hook("compaction-primer.py", _precompact())
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]

    named = set(re.findall(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:agent|cop))\b", ctx))
    assert named, f"standing orders name no verification agent at all: {ctx}"

    installed = {p.stem for p in (Path.home() / ".claude" / "agents").glob("*.md")}
    if not installed:
        pytest.skip("no agents installed; nothing to resolve names against")

    missing = sorted(n for n in named if n not in installed)
    assert not missing, (
        f"standing orders name agents that do not exist: {missing}; "
        f"installed: {sorted(installed)}"
    )


def test_standing_orders_mention_consult():
    result = run_hook("compaction-primer.py", _precompact())
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]
    assert "CONSULT" in ctx


def test_no_stderr_output():
    result = run_hook("compaction-primer.py", _precompact())
    assert result.returncode == 0
    assert result.stderr == b""
