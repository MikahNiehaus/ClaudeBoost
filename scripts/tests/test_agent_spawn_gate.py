"""
Tests for scripts/agent-spawn-gate.py (PreToolUse/Task hook).

Phase A — base behavior:
  - Prompt with RAG context HTTP call + project_path  -> exit 0
  - Prompt missing RAG context call entirely          -> exit 2
  - Prompt has context call but missing project_path  -> exit 2
  - architect-agent spawn without PROPOSAL_ONLY       -> exit 2
  - architect-agent spawn with full contract          -> exit 0

Phase B — evaluator routing:
  - NEEDS_VERIFICATION flag set, non-evaluator spawn  -> exit 2
  - NEEDS_VERIFICATION flag set, evaluator spawn      -> exit 0, flag cleared
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, run_hook, pretooluse

# A minimal prompt that satisfies all base checks (no active workspace assumed)
_BASE_PROMPT = (
    "curl -s -X POST http://127.0.0.1:8612/context "
    "-H 'Content-Type: application/json' "
    "-d '{\"agent\":\"test-agent\",\"project_path\":\"/test/project\"}'"
)


def _spawn(prompt: str, description: str = "test spawn") -> dict:
    return pretooluse("Task", {
        "prompt": prompt,
        "description": description,
        "subagent_type": "general-purpose",
    })


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_passes_with_http_context_call():
    """Prompt includes the HTTP context call with project_path — should pass."""
    result = run_hook("agent-spawn-gate.py", _spawn(_BASE_PROMPT))
    assert result.returncode == 0
    assert result.stderr == b""


def test_passes_with_legacy_rag_context():
    """Legacy rag_context keyword still accepted for backward compat."""
    prompt = "Call rag_context with project_path='/test/project' as first action"
    result = run_hook("agent-spawn-gate.py", _spawn(prompt))
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Failure: missing RAG context call
# ---------------------------------------------------------------------------

def test_blocks_missing_rag_context():
    """Prompt with no RAG context mention should exit 2 with an informative nudge."""
    result = run_hook("agent-spawn-gate.py", _spawn("Do some work and report findings."))
    assert result.returncode == 2
    assert b"does not instruct" in result.stderr or b"RAG context" in result.stderr.lower()


def test_blocks_missing_project_path():
    """Context call present but project_path missing exits 2."""
    prompt = "POST http://127.0.0.1:8612/context with {\"agent\":\"test\"}"
    result = run_hook("agent-spawn-gate.py", _spawn(prompt))
    assert result.returncode == 2
    assert b"project_path" in result.stderr


# ---------------------------------------------------------------------------
# Failure: architect-agent contract
# ---------------------------------------------------------------------------

def test_blocks_architect_missing_proposal_only():
    """architect-agent spawn without PROPOSAL_ONLY in prompt exits 2."""
    prompt = (
        _BASE_PROMPT + "\n"
        "You are architect-agent. Review scripts/foo.py:1 and scripts/bar.py:50."
    )
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt, description="architect-agent spawn"),
    )
    assert result.returncode == 2
    assert b"PROPOSAL_ONLY" in result.stderr


def test_passes_architect_with_full_contract():
    """architect-agent spawn with PROPOSAL_ONLY + 2 citations exits 0."""
    prompt = (
        _BASE_PROMPT + "\n"
        "PROPOSAL_ONLY\n"
        "Review scripts/agent-spawn-gate.py:1 and scripts/verify-gate-cmd.py:50."
    )
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt, description="architect-agent spawn"),
    )
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Phase B: evaluator routing gate
# ---------------------------------------------------------------------------

def _write_flag(boost_home: Path) -> Path:
    flag = boost_home / "state" / "needs-verification.json"
    flag.write_text(
        json.dumps({"flagged_at": "2026-01-01T00:00:00Z", "finding_summary": "test finding"}),
        encoding="utf-8",
    )
    return flag


def test_blocks_when_verification_pending(boost_home):
    """With needs-verification.json set, non-evaluator spawns are blocked."""
    _write_flag(boost_home)
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT, description="some other agent"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 2
    assert b"NEEDS_VERIFICATION" in result.stderr


def test_passes_evaluator_spawn_and_clears_flag(boost_home):
    """Evaluator-agent spawns pass and clear the flag."""
    flag = _write_flag(boost_home)
    assert flag.exists()

    prompt = _BASE_PROMPT + "\nYou are spawning evaluator-agent to verify findings."
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt, description="evaluator-agent verification"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert not flag.exists(), "flag should be cleared after evaluator-agent spawn"


def test_passes_normally_without_flag(boost_home):
    """When no flag file exists, normal spawns are unaffected."""
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
