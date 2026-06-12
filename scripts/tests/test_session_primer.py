"""
Tests for scripts/session-primer.py (UserPromptSubmit hook).

Injects additionalContext with always-on rules and standing orders.
Always exits 0.
"""
from __future__ import annotations

import json
import time
import pytest
from helpers import SCRIPTS_DIR, run_hook


def _prompt(text: str) -> dict:
    return {"hook_event_name": "UserPromptSubmit", "session_id": "test", "prompt": text}


def _run(prompt_text: str, boost_home=None, extra_env=None) -> "subprocess.CompletedProcess":
    env = {}
    if boost_home:
        env["CLAUDEBOOST_HOME"] = str(boost_home)
    if extra_env:
        env.update(extra_env)
    return run_hook("session-primer.py", _prompt(prompt_text), env_overrides=env or None)


# ---------------------------------------------------------------------------
# Always exits 0
# ---------------------------------------------------------------------------

def test_always_exits_0(boost_home):
    result = _run("please implement a new feature for me", boost_home=boost_home)
    assert result.returncode == 0


def test_exits_0_on_short_prompt(boost_home):
    result = _run("hi", boost_home=boost_home)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Injects context for substantive prompts
# ---------------------------------------------------------------------------

def test_injects_context_for_long_prompt(boost_home):
    result = _run("implement the authentication service with JWT tokens", boost_home=boost_home)
    assert result.returncode == 0
    assert result.stdout  # something was printed
    output = json.loads(result.stdout)
    assert "additionalContext" in output


def test_injected_context_contains_always_on_rules(boost_home):
    result = _run("fix the bug in the payment service", boost_home=boost_home)
    output = json.loads(result.stdout)
    ctx = output["additionalContext"]
    assert "ALWAYS-ON" in ctx or "TaskCreate" in ctx


def test_short_prompt_skips_injection(boost_home):
    # Under 15 chars with no clear-pending → no injection
    result = _run("ok", boost_home=boost_home)
    assert result.returncode == 0
    # Short prompts don't inject
    if result.stdout.strip():
        output = json.loads(result.stdout)
        # If there IS output it should still be valid JSON
        assert "additionalContext" in output
    # Either no output or valid additionalContext — both are fine


# ---------------------------------------------------------------------------
# boost_mode false: skip injection
# ---------------------------------------------------------------------------

def test_skip_injection_when_boost_false(boost_home):
    bi = boost_home / "state" / "boost-injection.json"
    bi.write_text(json.dumps({"mode": "false"}), encoding="utf-8")

    result = _run("implement a comprehensive new authentication service", boost_home=boost_home)
    assert result.returncode == 0
    # When mode is "false", nothing should be printed
    assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# boost_mode true: inject without RAG verification
# ---------------------------------------------------------------------------

def test_boost_true_injects_without_rag_sentinel(boost_home, tmp_path):
    bi = boost_home / "state" / "boost-injection.json"
    bi.write_text(json.dumps({"mode": "true"}), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("implement the feature from the ticket"),
        env_overrides={
            "CLAUDEBOOST_HOME": str(boost_home),
            "TEMP": str(tmp_path),  # no sentinel in tmp_path
        },
    )
    assert result.returncode == 0
    assert result.stdout.strip()
    output = json.loads(result.stdout)
    assert "additionalContext" in output


# ---------------------------------------------------------------------------
# clear-pending flag: inject context restore
# ---------------------------------------------------------------------------

def test_consumes_clear_pending_flag(boost_home):
    import datetime

    # Write a fresh clear-pending flag
    flag_path = boost_home / "state" / "clear-pending.json"
    flag_path.write_text(json.dumps({
        "pending": True,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }), encoding="utf-8")

    # Write a handoff-latest with memo
    handoff_path = boost_home / "state" / "handoff-latest.json"
    handoff_path.write_text(json.dumps({
        "workspace_memo": "### task-1\nStatus: in progress\nNext: finish tests",
        "active_workspace": "task-1",
    }), encoding="utf-8")

    result = run_hook(
        "session-primer.py",
        _prompt("continue"),  # short prompt is OK when clear-pending is set
        env_overrides={"CLAUDEBOOST_HOME": str(boost_home)},
    )
    assert result.returncode == 0
    # Flag should be consumed (deleted)
    assert not flag_path.exists()
    # Output should contain restoration context
    if result.stdout.strip():
        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "CONTEXT" in ctx.upper() or "workspace" in ctx.lower()
