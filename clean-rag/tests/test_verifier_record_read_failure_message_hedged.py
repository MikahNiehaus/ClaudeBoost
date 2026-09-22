"""Regression test for the nit fix in _explain_empty_report.

A prior bad-cop pass found: the "could not read" diagnostic unconditionally
named a file lock as the cause ("Another process holding the file is the
usual cause on Windows and clears in milliseconds, so run the cop again"),
regardless of what read_error actually said. Pointing agent_transcript_path
at a real directory produces a PermissionError, not a lock, and the old
message printed the lock explanation anyway, advice that does not apply and
that "run the cop again" will not fix.

The fix conditions the advice on the two things it could actually be,
without asserting which one this is. This drives the real hook as a real
subprocess, with a scrubbed environment (no ambient PATH beyond the bare
minimum needed to resolve the interpreter and stdlib), against a real
directory, the same input that produced the original bug.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "verifier-record.py"


def _scrubbed_env():
    """Only what the interpreter and stdlib need to start and resolve
    imports. No inherited PATH, no ambient token, nothing this hook's own
    correctness could accidentally depend on without declaring it."""
    env = {}
    for key in ("SYSTEMROOT", "PATHEXT"):
        if key in os.environ:
            env[key] = os.environ[key]
    # sys.executable is an absolute path, so PATH is not needed to find it.
    return env


def _run_against(agent_transcript_path: str) -> subprocess.CompletedProcess:
    payload = {
        "hook_event_name": "SubagentStop",
        "agent_type": "bad-cop",
        "agent_id": "a1b2c3",
        "agent_transcript_path": agent_transcript_path,
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=120,
        env=_scrubbed_env(),
    )


def test_a_directory_path_gets_a_hedged_message_not_a_fixed_lock_claim(tmp_path):
    real_dir = tmp_path / "not_a_transcript"
    real_dir.mkdir()

    proc = _run_against(str(real_dir))

    assert proc.returncode == 0
    stderr = proc.stderr
    assert "could not read" in stderr
    # The old bug: asserted the lock cause unconditionally, no matter what
    # read_error actually said.
    assert (
        "Another process holding the file is the usual cause"
        not in stderr
    ), "reintroduced the unconditional fixed-cause claim"
    # The fix: names both candidate causes, conditioned on "if that path is
    # a real transcript" / "if it is not", rather than asserting either one.
    assert "If that path is a real transcript" in stderr
    assert "If it is not" in stderr
    assert "the payload named the wrong path" in stderr


def test_the_hedged_message_still_names_a_next_action(tmp_path):
    """Property 2: hedging must not degrade into a message that recommends
    nothing. Both branches of the hedge must still tell the reader something
    to do, not just list possibilities."""
    real_dir = tmp_path / "not_a_transcript"
    real_dir.mkdir()

    proc = _run_against(str(real_dir))
    stderr = proc.stderr

    # Branch one: it might be a lock, so retrying is the action.
    assert "run the cop again" in stderr
    # Branch two: it might be a wrong path, so retrying will not help, which
    # is itself the actionable information (do not waste time retrying).
    assert "running the cop again will fail the same way" in stderr


def test_a_genuinely_missing_transcript_prints_no_diagnostic_at_all(tmp_path):
    """FileNotFoundError is the ordinary case (an agent that never handed
    back), not a read failure, and must stay silent. This pins that the
    hedge did not widen when the read error is empty."""
    missing = tmp_path / "does_not_exist.jsonl"

    proc = _run_against(str(missing))

    assert proc.returncode == 0
    assert "could not read" not in proc.stderr
