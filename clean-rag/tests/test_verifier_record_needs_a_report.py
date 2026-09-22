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


def _handback_line(message):
    """One transcript entry of the shape a real SubagentHandback call has.

    Taken from a real bad-cop transcript read on 2026-09-18, line 194 of
    agent-a484f312215a83f2c.jsonl: the report is the `input.message` of a
    tool_use block named SubagentHandback, not assistant text.
    """
    return json.dumps({
        "isSidechain": True,
        "agentId": "a484f312215a83f2c",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_01NbmW32gsh",
             "name": "SubagentHandback", "input": {"message": message}},
        ]},
    })


def _chat_line(text):
    """Plain assistant text, which is what last_assistant_message captures."""
    return json.dumps({"message": {"role": "assistant",
                                   "content": [{"type": "text", "text": text}]}})


# What a real agent says in chat AFTER handing back, sometimes minutes later in
# reply to a delayed background task notification. It carries no marker, and
# the old code read exactly this and nothing else.
TRAILING_CHAT = (
    "No action needed. My review is already complete and the report was "
    "delivered via SubagentHandback."
)


def _agent_transcript(tmp_path, *lines, name="agent-a1b2c3.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_subagent_stop_reads_the_handback_from_the_agent_transcript(tmp_path, session):
    """The report is the handback's input.message, even with chat after it."""
    _make_target(tmp_path)
    tr = _agent_transcript(
        tmp_path,
        _chat_line("an earlier turn"),
        _handback_line(REAL_REPORT),
        json.dumps({"message": {"role": "user", "content": [
            {"type": "tool_result", "content": "Report delivered to your caller."}]}}),
        _chat_line(TRAILING_CHAT),
    )
    r = _subagent_stop(tmp_path, session, agent_transcript_path=str(tr))
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None, "the handback in the agent transcript was not read"
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


def test_the_closing_chat_message_can_never_stamp(tmp_path, session):
    """A VERIFIED line in ordinary chat is not a report and must not stamp.

    This is the forgery this record exists to prevent. An agent that never
    handed back, or one talked into writing the marker in conversation, would
    otherwise stamp the gate on text nothing verified. Only a real handback
    counts, so there is deliberately no fallback to assistant text.
    """
    _make_target(tmp_path)
    tr = _agent_transcript(tmp_path, _chat_line(REAL_REPORT))
    r = _subagent_stop(
        tmp_path, session,
        agent_transcript_path=str(tr),
        last_assistant_message=REAL_REPORT,
    )
    assert r.returncode == 0
    assert _record_for(session) is None, "chat text was accepted as a report"


def test_the_parent_transcript_is_not_read(tmp_path, session):
    """transcript_path is this session's file, not the agent's. Reading it was
    the second half of the bug: it never held the subagent's handback."""
    _make_target(tmp_path)
    parent = _agent_transcript(tmp_path, _handback_line(REAL_REPORT),
                               name="parent.jsonl")
    r = _subagent_stop(tmp_path, session, transcript_path=str(parent))
    assert r.returncode == 0
    assert _record_for(session) is None, "the parent transcript was read"


def test_the_last_handback_wins_when_there_are_several(tmp_path, session):
    _make_target(tmp_path)
    tr = _agent_transcript(
        tmp_path,
        _handback_line(HANDOFF_REPORT),
        _chat_line(TRAILING_CHAT),
        _handback_line(REAL_REPORT),
    )
    r = _subagent_stop(tmp_path, session, agent_transcript_path=str(tr))
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"], \
        "an earlier handback won over the last one"


def test_a_tool_call_that_is_not_a_handback_is_never_the_report(tmp_path, session):
    """Only SubagentHandback counts, not whichever tool_use happens to be last.

    An agent keeps working after it hands back: it answers a delayed background
    task notification, sends a message, runs one more command. Those are
    tool_use blocks too, and some of them carry an `input.message` field of
    their own, so matching on block type alone picks up the wrong one.
    """
    _make_target(tmp_path)
    other_tool = json.dumps({"message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_zzz", "name": "SendMessage",
         "input": {"to": "someone", "message": REAL_REPORT}},
    ]}})
    tr = _agent_transcript(tmp_path, _handback_line(HANDOFF_REPORT), other_tool)
    r = _subagent_stop(tmp_path, session, agent_transcript_path=str(tr))
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None
    assert rec["stamps"][0]["covers"] == [], \
        "a non handback tool call was read as the report"


def test_a_handback_far_past_the_tail_window_is_still_found(tmp_path, session):
    """A real transcript is megabytes. The reader takes the tail first, so the
    whole file retry is the only thing that finds a handback above it, and a
    silent failure here would look exactly like a normal no-report run."""
    _make_target(tmp_path)
    padding = [_chat_line("x" * 20000) for _ in range(80)]
    tr = _agent_transcript(
        tmp_path,
        _handback_line(REAL_REPORT),
        *padding,
    )
    assert tr.stat().st_size > 1_000_000, "the padding did not exceed the window"
    r = _subagent_stop(tmp_path, session, agent_transcript_path=str(tr))
    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None, "the whole file retry did not fire"
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


# The tail read is a size optimization with no visible effect on the answer, so
# driving the hook as a subprocess cannot tell a working one from a broken one.
# These import the module and check it directly.

def _hook_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_record_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_tail_read_does_not_load_the_whole_file(tmp_path):
    """A real transcript is megabytes and this runs on every completion."""
    vr = _hook_module()
    p = tmp_path / "big.jsonl"
    p.write_text("\n".join(_chat_line("x" * 5000) for _ in range(600)) + "\n",
                 encoding="utf-8")
    assert p.stat().st_size > vr._TAIL_BYTES, "the fixture is not big enough to test this"

    lines, first_line_may_be_cut, read_error = vr._transcript_lines(p)
    got = len(lines)
    assert got < 600, f"read all {got} lines, so the tail read is not working"
    assert got > 0, "read nothing at all"
    assert first_line_may_be_cut, "a seeked read must say its first line can be a fragment"
    assert read_error == "", f"a healthy read reported a failure: {read_error}"


def test_a_cut_exactly_on_a_line_boundary_keeps_that_whole_line(tmp_path):
    """The one case where the slicing is observable at all.

    _handback_report retries on the whole file when the tail misses, so a
    dropped line there costs a wasted read and nothing else. Checking the
    reader itself is the only way to see it, and a boundary cut is the case
    that a "drop the first line, it is a fragment" reader gets wrong.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    first, last = _chat_line("first"), _chat_line("last")
    # Bytes, not write_text: on Windows that translates \n to \r\n, which puts
    # the byte arithmetic below two bytes out and makes this test lie.
    p.write_bytes((first + "\n" + last + "\n").encode("utf-8"))

    # Seek exactly to the byte after the first newline, so the chunk begins
    # with a complete line rather than a fragment.
    window = len(last.encode("utf-8")) + 1
    saved = vr._TAIL_BYTES
    try:
        vr._TAIL_BYTES = window
        lines, _, _ = vr._transcript_lines(p)
    finally:
        vr._TAIL_BYTES = saved

    assert last in lines, "a complete line was dropped as if it were a fragment"


def test_the_handback_is_found_whatever_the_cut_lands_on(tmp_path):
    """The seek lands at an arbitrary byte, including exactly on a newline.

    Sweeping the window a byte at a time across a whole line walks the cut
    through every position in it, which is where an off by one in the slicing
    would drop a complete entry or keep a fragment that parses.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join([
        _chat_line("before"),
        _handback_line(REAL_REPORT),
        _chat_line("after one"),
        _chat_line("after two"),
    ]) + "\n", encoding="utf-8")

    size = p.stat().st_size
    saved = vr._TAIL_BYTES
    try:
        for window in range(1, size + 2):
            vr._TAIL_BYTES = window
            got = vr._handback_report(str(p))
            assert got == REAL_REPORT, \
                f"window={window} of {size} returned {len(got)} chars, not the report"
    finally:
        vr._TAIL_BYTES = saved


def test_no_handback_stays_empty_at_every_cut(tmp_path):
    """The sweep must not manufacture a report out of a truncated line."""
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(_chat_line(t) for t in ("one", "two", REAL_REPORT)) + "\n",
                 encoding="utf-8")

    size = p.stat().st_size
    saved = vr._TAIL_BYTES
    try:
        for window in range(1, size + 2):
            vr._TAIL_BYTES = window
            assert vr._handback_report(str(p)) == "", f"window={window} invented a report"
    finally:
        vr._TAIL_BYTES = saved
