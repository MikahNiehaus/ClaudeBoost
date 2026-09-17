"""A completion with no report must record nothing, not an empty stamp.

An empty stamp is worse than no stamp. loop_stage() reads a bad-cop entry with
an empty covers list as STAGE_BUGS_FOUND, so a completion that carried no report
becomes indistinguishable from a real HANDOFF and routes to good-cop on evidence
that does not exist. Every session from 2026-08-28 onward recorded 0 of N stamps
with a covers list because of this.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
HOOK = HOOKS / "verifier-record.py"

REAL_REPORT = """REVIEW SCOPE: the locking change

Ran it for real:

    $ python -m pytest clean-rag/tests/test_log_tail_rotation.py -q
    11 passed in 0.81s

VERIFIED: clean-rag/cli/log_tail.py
"""

HANDOFF_REPORT = """REVIEW SCOPE: the locking change

[High] Something real, proven by running it:

    $ python probe.py
    reproduced

HANDOFF: 1 real finding
"""

# What a backgrounded spawn actually delivers instead of a report.
LAUNCH_ACK = "Async agent launched successfully. The agent is working in the background."


def _run(tmp_path, report, session, agent="bad-cop"):
    payload = {
        "session_id": session,
        "tool_name": "Task",
        "cwd": str(tmp_path),
        "tool_input": {"subagent_type": agent, "prompt": "review it"},
        "tool_response": report,
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _record_for(session):
    key = hashlib.sha256(session.encode()).hexdigest()[:16]
    state = HOOKS.parent / "state" / "verifier" / f"session-{key}.json"
    if not state.exists():
        return None
    return json.loads(state.read_text(encoding="utf-8"))


@pytest.fixture
def session(request):
    """A throwaway session id, cleaned up so the live record is untouched."""
    sid = f"pytest-{request.node.name}-{id(request)}"
    yield sid
    key = hashlib.sha256(sid.encode()).hexdigest()[:16]
    p = HOOKS.parent / "state" / "verifier" / f"session-{key}.json"
    if p.exists():
        p.unlink()


def test_a_launch_acknowledgement_records_nothing(tmp_path, session):
    """The exact text a backgrounded spawn delivers."""
    r = _run(tmp_path, LAUNCH_ACK, session)
    assert r.returncode == 0
    assert _record_for(session) is None, "an empty stamp was written"


def test_it_says_why_and_names_the_cause(tmp_path, session):
    r = _run(tmp_path, LAUNCH_ACK, session)
    assert "backgrounded" in r.stderr
    assert "foreground" in r.stderr


def test_an_empty_report_records_nothing(tmp_path, session):
    r = _run(tmp_path, "", session)
    assert r.returncode == 0
    assert _record_for(session) is None


def test_a_real_verified_report_still_records_its_files(tmp_path, session):
    """The guard must not eat a legitimate stamp."""
    (tmp_path / "clean-rag" / "cli").mkdir(parents=True)
    (tmp_path / "clean-rag" / "cli" / "log_tail.py").write_text("x = 1\n", encoding="utf-8")

    r = _run(tmp_path, REAL_REPORT, session)
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None, "a real VERIFIED report was dropped"
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


def test_a_handoff_still_records_with_no_files(tmp_path, session):
    """HANDOFF legitimately carries no file list, and that drives the routing."""
    r = _run(tmp_path, HANDOFF_REPORT, session)
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None, "a real HANDOFF was dropped, which breaks the routing"
    assert rec["stamps"][0]["covers"] == []


def _subagent_stop(tmp_path, session, **extra):
    payload = {
        "session_id": session,
        "agent_type": "bad-cop",
        "agent_id": "a1b2c3",
        "cwd": str(tmp_path),
        "transcript_path": "",
        **extra,
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=120,
    )


def _make_target(tmp_path):
    (tmp_path / "clean-rag" / "cli").mkdir(parents=True, exist_ok=True)
    (tmp_path / "clean-rag" / "cli" / "log_tail.py").write_text("x = 1\n", encoding="utf-8")


def test_subagent_stop_records_an_inline_report(tmp_path, session):
    _make_target(tmp_path)
    r = _subagent_stop(tmp_path, session, last_assistant_message=REAL_REPORT)
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


def test_subagent_stop_falls_back_to_the_transcript(tmp_path, session):
    """The key name is not confirmed in the docs, so this path carries the fix."""
    _make_target(tmp_path)
    tr = tmp_path / "transcript.jsonl"
    tr.write_text("\n".join([
        json.dumps({"message": {"role": "user", "content": "go"}}),
        json.dumps({"message": {"role": "assistant",
                                "content": [{"type": "text", "text": "an earlier turn"}]}}),
        json.dumps({"message": {"role": "assistant",
                                "content": [{"type": "text", "text": REAL_REPORT}]}}),
    ]), encoding="utf-8")

    r = _subagent_stop(tmp_path, session, transcript_path=str(tr))
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None, "the transcript fallback did not fire"
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


def test_subagent_stop_with_no_report_records_nothing(tmp_path, session):
    r = _subagent_stop(tmp_path, session)
    assert r.returncode == 0
    assert _record_for(session) is None


def test_subagent_stop_ignores_agents_that_are_not_cops(tmp_path, session):
    r = _subagent_stop(tmp_path, session, agent_type="swiper",
                       last_assistant_message=REAL_REPORT)
    assert r.returncode == 0
    assert _record_for(session) is None


def test_a_missing_transcript_is_not_an_error(tmp_path, session):
    r = _subagent_stop(tmp_path, session,
                       transcript_path=str(tmp_path / "nope.jsonl"))
    assert r.returncode == 0
    assert _record_for(session) is None


def test_the_hook_never_fails_the_turn(tmp_path, session):
    for junk in ("null", "[]", '"a string"', "not json at all"):
        r = subprocess.run(
            [sys.executable, str(HOOK)],
            input=junk, capture_output=True, text=True, timeout=120,
        )
        assert r.returncode == 0, f"non-zero on {junk!r}"
