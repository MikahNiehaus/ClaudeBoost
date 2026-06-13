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
  - NEEDS_VERIFICATION + audit-in-progress both set   -> exit 0 (audit bypasses gate)
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

def test_passes_with_http_context_call(boost_home):
    """Prompt includes the HTTP context call with project_path — should pass."""
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert result.stderr == b""


def test_passes_with_workspace_path_in_prompt(boost_home):
    """Regression: a prompt that already includes workspace_path must pass.

    A function-local `import os` inside the workspace_path branch made `os`
    local to the whole function. When the branch was skipped (workspace_path
    present), the later os.environ access raised UnboundLocalError and the
    hook crashed with a traceback on every well-formed spawn.
    """
    prompt = (
        _BASE_PROMPT.replace(
            '"project_path":"/test/project"',
            '"project_path":"/test/project","workspace_path":"/test/project/workspace/task-1"',
        )
    )
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert b"Traceback" not in result.stderr
    assert result.stderr == b""


def test_passes_with_legacy_rag_context(boost_home):
    """Legacy rag_context keyword still accepted for backward compat."""
    prompt = "Call rag_context with project_path='/test/project' as first action"
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
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


def test_passes_architect_with_full_contract(boost_home):
    """architect-agent spawn with PROPOSAL_ONLY + 2 citations exits 0."""
    prompt = (
        _BASE_PROMPT + "\n"
        "PROPOSAL_ONLY\n"
        "Review scripts/agent-spawn-gate.py:1 and scripts/verify-gate-cmd.py:50."
    )
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt, description="architect-agent spawn"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
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


def test_passes_verdict_spawn_and_clears_flag(boost_home):
    """A verdict-synthesis spawn counts as the evaluator pass and clears the flag."""
    flag = _write_flag(boost_home)
    assert flag.exists()

    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT, description="Opus verdict synthesis"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    assert not flag.exists(), "flag should be cleared after a verdict spawn"


def test_passes_normally_without_flag(boost_home):
    """When no flag file exists, normal spawns are unaffected."""
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0


def test_passes_during_active_audit(boost_home):
    """NEEDS_VERIFICATION flag does not block spawns when audit-in-progress.json is active."""
    _write_flag(boost_home)
    audit_flag = boost_home / "state" / "audit-in-progress.json"
    audit_flag.write_text('{"active":true}', encoding="utf-8")
    try:
        result = run_hook(
            "agent-spawn-gate.py",
            _spawn(_BASE_PROMPT, description="audit dimension: security analysis"),
            env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
        )
        assert result.returncode == 0
    finally:
        audit_flag.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Exception handling / edge cases (covers missed lines 53-54, 61-62, 109-114,
# 121-122, 168-169)
# ---------------------------------------------------------------------------

def test_handles_invalid_json_stdin():
    """Invalid JSON on stdin → payload={} → exit 2 (no RAG context call detected)."""
    import subprocess as _sp
    script = SCRIPTS_DIR / "agent-spawn-gate.py"
    result = _sp.run(
        ["python", str(script)],
        input=b"this is not json",
        capture_output=True,
    )
    # No RAG context call in the (empty) payload → blocked
    assert result.returncode == 2


def test_log_exception_does_not_crash_hook(tmp_path):
    """_log_usage exception (state dir is a file not dir) is silently swallowed."""
    # Make state a regular file so opening agent-usage.jsonl inside it fails
    state_as_file = tmp_path / "state"
    state_as_file.write_text("not a dir")
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn("no rag here", description="test"),
        env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
    )
    # Hook should still exit 2 (no RAG) — the log write failure is silently ignored
    assert result.returncode == 2


def test_workspace_path_looked_up_via_registry(boost_home, tmp_path):
    """active-workspace.json with workspace ID (no path) triggers registry lookup."""
    state_dir = boost_home / "state"
    state_dir.mkdir(exist_ok=True)
    # Old schema: workspace ID only, no workspace_path
    (state_dir / "active-workspace.json").write_text(
        json.dumps({"workspace": "test-task-2026"}), encoding="utf-8"
    )
    # Registry maps the ID to a real workspace path
    ws_path = str(tmp_path / "workspace" / "test-task-2026")
    reg = {"test-task-2026": {"workspace_path": ws_path, "project_path": str(tmp_path)}}
    (state_dir / "workspaces.json").write_text(json.dumps(reg), encoding="utf-8")

    # Prompt has context call + project_path but NOT workspace_path
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    # workspace_path was found via registry → nudge fires → exit 2
    assert result.returncode == 2
    assert b"workspace_path" in result.stderr


def test_handles_corrupt_active_workspace_json(boost_home):
    """Corrupt active-workspace.json is silently ignored — hook passes normally."""
    state_dir = boost_home / "state"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "active-workspace.json").write_text("NOT JSON", encoding="utf-8")

    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(_BASE_PROMPT),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    # Corrupt file → exception swallowed → no workspace_path nudge → passes
    assert result.returncode == 0


def test_evaluator_unlink_exception_silently_ignored(boost_home):
    """flag.unlink() raising (flag is a directory) is silently swallowed — hook exits 0."""
    flag_path = boost_home / "state" / "needs-verification.json"
    flag_path.mkdir(parents=True, exist_ok=True)  # directory, not file

    prompt = _BASE_PROMPT + "\nYou are spawning evaluator-agent to verify findings."
    result = run_hook(
        "agent-spawn-gate.py",
        _spawn(prompt, description="evaluator-agent verification"),
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    # Evaluator spawn passes even when unlink raises
    assert result.returncode == 0
