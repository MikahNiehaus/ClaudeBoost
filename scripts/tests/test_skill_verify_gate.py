"""
Tests for scripts/skill-verify-gate.py (PreToolUse hook on the Skill tool).

This file exists because the hook had no test at all, and it was changed from
a hard block to a nudge. Two defects it never covered, both live in the shipped
hook until now:

  1. It exited 2 and refused an action skill. A verifier gate refusing work is
     the enforcement shape this project has reverted twice; only security
     guards refuse. See clean-rag/hooks/verifier-gate.py's own docstring.
  2. Its refusal message told the operator to spawn `evaluator-agent`, which
     has never existed in this repo, and claimed the gate "clears
     automatically when the evaluator runs". Clearing is verify-gate-cmd.py's
     job, and that hook matched only the literal words "evaluator" and
     "verdict" in a Task description, so a real quick-cop spawn described in
     ordinary prose left the flag set forever.

The remedy-is-performable test below is the one that matters. A gate whose
stated escape route cannot be taken is worse than no gate: it trains the
operator to ignore it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, hook_env, run_hook

AGENTS_DIR = Path.home() / ".claude" / "agents"

# Straight from the hook's own docstring.
ACTION_SKILL = "qa"
PASSTHROUGH_SKILL = "audit"


def _skill(name: str) -> dict:
    return {"tool_name": "Skill", "tool_input": {"skill": name}}


def _flag(home: Path, summary: str = "BLOCKER: example finding") -> Path:
    path = home / "state" / "needs-verification.json"
    path.write_text(json.dumps({
        "flagged_at": "2026-09-08T00:00:00Z",
        "tool_name": "bad-cop review",
        "finding_summary": summary,
    }), encoding="utf-8")
    return path


def _run(home: Path, skill: str):
    return run_hook(
        "skill-verify-gate.py",
        _skill(skill),
        env_overrides={"CLAUDEBOOST_HOME": str(home)},
        cwd=home,
    )


# ---------------------------------------------------------------------------
# Silence when there is nothing to say
# ---------------------------------------------------------------------------

def test_silent_when_no_flag(boost_home):
    result = _run(boost_home, ACTION_SKILL)
    assert result.returncode == 0
    assert result.stderr == b""


def test_silent_for_a_passthrough_skill(boost_home):
    _flag(boost_home)
    result = _run(boost_home, PASSTHROUGH_SKILL)
    assert result.returncode == 0
    assert result.stderr == b""


def test_silent_while_an_audit_batch_is_in_flight(boost_home):
    _flag(boost_home)
    (boost_home / "state" / "audit-in-progress.json").write_text("{}", encoding="utf-8")
    result = _run(boost_home, ACTION_SKILL)
    assert result.returncode == 0
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# The behaviour that changed
# ---------------------------------------------------------------------------

def test_nudges_but_does_not_block_an_action_skill(boost_home):
    """Exit 0, not 2.

    Claude Code treats 2 from a PreToolUse hook as a refusal. This gate makes a
    judgement call about whether findings were checked, and judgement calls
    nudge here. Reverting this to 2 should fail this test loudly.
    """
    _flag(boost_home)
    result = _run(boost_home, ACTION_SKILL)
    assert result.returncode == 0, (
        "the gate must not refuse the skill; got exit "
        f"{result.returncode}"
    )
    assert result.stderr != b"", "it should still say something"


def test_the_nudge_says_it_is_not_blocking(boost_home):
    _flag(boost_home)
    err = _run(boost_home, ACTION_SKILL).stderr.decode("utf-8", "replace").lower()
    assert "nudge, not a block" in err, err


def test_the_nudge_shows_the_finding(boost_home):
    _flag(boost_home, summary="BLOCKER: sql injection at app.py:42")
    err = _run(boost_home, ACTION_SKILL).stderr.decode("utf-8", "replace")
    assert "sql injection at app.py:42" in err, err


# ---------------------------------------------------------------------------
# The remedy has to be performable. This is the real regression guard.
# ---------------------------------------------------------------------------

def test_every_agent_the_nudge_names_actually_exists(boost_home):
    """No phantom agents in operator-facing text.

    The old message named `evaluator-agent`. Nothing resolved that name, so
    following the instruction verbatim did nothing and the block persisted.
    """
    _flag(boost_home)
    err = _run(boost_home, ACTION_SKILL).stderr.decode("utf-8", "replace")

    named = set(re.findall(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:agent|cop))\b", err))
    assert named, f"the nudge names no agent to spawn: {err}"

    if not AGENTS_DIR.is_dir():
        pytest.skip("no agent directory on this machine")
    installed = {p.stem for p in AGENTS_DIR.glob("*.md")}
    if not installed:
        pytest.skip("no agents installed; nothing to resolve names against")

    missing = sorted(n for n in named if n not in installed)
    assert not missing, (
        f"the nudge tells the operator to spawn {missing}, which do not exist; "
        f"installed: {sorted(installed)}"
    )


def test_it_does_not_promise_automatic_clearing_it_cannot_deliver(boost_home):
    """The old text said the gate "clears automatically when the evaluator runs".

    This hook clears nothing. verify-gate-cmd.py does, on a Task completion.
    Claiming otherwise sent operators looking for behaviour that was not there.
    """
    _flag(boost_home)
    err = _run(boost_home, ACTION_SKILL).stderr.decode("utf-8", "replace").lower()
    assert "clears automatically" not in err, err


# ---------------------------------------------------------------------------
# Payload shapes. json.loads accepts any JSON value, not just an object.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "", "null", "[]", '"a string"', "17", "not json at all", "{}",
    '{"tool_input": null}', '{"tool_input": []}',
    '{"tool_name": "Skill"}',
])
def test_never_crashes_on_a_malformed_payload(boost_home, raw):
    """Exit 1 is a crash, not a block, and it would be silent here.

    Same class as the five hooks fixed in clean-rag/hooks/ this round.
    """
    _flag(boost_home)
    # hook_env, not os.environ. A subprocess test that inherits the ambient
    # environment passes for reasons it never declared, which is the failure
    # scripts/tests/test_helpers_env.py exists to prevent. It caught this file.
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "skill-verify-gate.py")],
        input=raw, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env=hook_env({"CLAUDEBOOST_HOME": str(boost_home)}),
        cwd=str(boost_home), timeout=120,
    )
    assert proc.returncode == 0, (
        f"payload {raw!r} produced exit {proc.returncode}; stderr: {proc.stderr}"
    )
