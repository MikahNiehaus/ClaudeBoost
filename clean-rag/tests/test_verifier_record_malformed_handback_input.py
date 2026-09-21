"""Adversarial test written by bad-cop reviewing verifier-record.py's new
_scan_for_handback / _handback_report (see clean-rag/hooks/verifier-record.py).

_scan_for_handback guards every other field it reads off a transcript entry
with an isinstance() check (entry, msg, content, block are all checked before
use), except one: `block.get("input")`. When `input` is a truthy non-dict
value (a string is the realistic shape; a proxy or malformed replay of a
tool_use block), `(block.get("input") or {}).get("message")` raises
AttributeError, because a string has no `.get`.

That exception is not caught inside the scan, so it propagates out of
_handback_report, out of main(), to the top-level try/except in
verifier-record.py's `__main__` guard. The hook still exits 0 (per
correctness property 6), but the *scan stops entirely* at the malformed
entry: the reversed-order walk never reaches an earlier, perfectly valid
SubagentHandback further back in the same transcript. A completion that
genuinely called SubagentHandback with a real VERIFIED report is recorded as
if nothing had ever been reported, with no diagnostic pointing at the real
cause (the generic "could not stamp this agent completion" message, not the
specific "no closing stamp" nudge that a legitimately un-reported completion
gets).

This is exactly the failure class the whole diff exists to eliminate: a real
report silently not making it into the record.

The second half of the file covers the sibling exception site, where the line
fails json.loads outright rather than parsing into a shape the walk cannot
read. A truncated write, a stray BOM or a process killed mid line all land
there, and it swallowed them the same way. The tail seek makes one such line
expected on every large transcript, so the tests below pin both directions:
real corruption must produce a note, and the expected fragment must not.
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


def _record_for(session):
    key = hashlib.sha256(session.encode()).hexdigest()[:16]
    state = HOOKS.parent / "state" / "verifier" / f"session-{key}.json"
    if not state.exists():
        return None
    return json.loads(state.read_text(encoding="utf-8"))


@pytest.fixture
def session(request):
    sid = f"pytest-{request.node.name}-{id(request)}"
    yield sid
    key = hashlib.sha256(sid.encode()).hexdigest()[:16]
    p = HOOKS.parent / "state" / "verifier" / f"session-{key}.json"
    if p.exists():
        p.unlink()


def _make_target(tmp_path):
    (tmp_path / "clean-rag" / "cli").mkdir(parents=True, exist_ok=True)
    (tmp_path / "clean-rag" / "cli" / "log_tail.py").write_text("x = 1\n", encoding="utf-8")


def _handback_line(message):
    return json.dumps({
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_real", "name": "SubagentHandback",
             "input": {"message": message}},
        ]},
    })


def _malformed_handback_line(bad_input):
    """A SubagentHandback tool_use block whose `input` is not a dict.

    Anthropic's tool_use.input is documented as a JSON object, so this should
    not occur from the API in the ordinary case. It is realistic anyway: this
    hook reads a JSONL file that is not validated against that contract before
    the hook opens it (a corrupted write, a replayed/edited entry, a future
    client change), and every sibling field in this same function (entry, msg,
    content, block) is defended with an isinstance() check for exactly this
    kind of shape drift. `input` is the one field that is not.
    """
    return json.dumps({
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_bad", "name": "SubagentHandback",
             "input": bad_input},
        ]},
    })


def _subagent_stop(tmp_path, session, agent_transcript_path):
    payload = {
        "session_id": session,
        "agent_type": "bad-cop",
        "agent_id": "a1b2c3",
        "cwd": str(tmp_path),
        "transcript_path": "",
        "agent_transcript_path": agent_transcript_path,
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=120,
    )


def _hook_module():
    """The hook loaded in-process, for the seams a subprocess cannot reach.

    Same loader the sibling test file uses; the filename's hyphen means it
    cannot be imported normally.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_record_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: Every JSON type `input` can arrive as that is not a dict. `or {}` falls
#: through for each of them identically, so a guard written against `str`
#: alone leaves the same hole open for the rest.
BAD_INPUTS = [
    "a stray non-dict input, e.g. a corrupted replay",
    ["message", "as a list"],
    7,
    True,
]


@pytest.mark.parametrize("bad_input", BAD_INPUTS)
def test_a_malformed_later_handback_does_not_swallow_a_real_earlier_one(
    tmp_path, session, bad_input
):
    """A real, valid VERIFIED handback sits earlier in the transcript than a
    later, malformed tool_use block that also claims to be SubagentHandback.
    The real one must still be found and recorded.

    Reproduced directly against _scan_for_handback with a bare string `input`:

        AttributeError: 'str' object has no attribute 'get'

    and through the full hook subprocess, where the crash is caught by the
    top-level handler and turns into a silent non-stamp:

        [verifier-record] could not stamp this agent completion:
        AttributeError: 'str' object has no attribute 'get'. The verifier
        gate will treat the reviewed files as unverified.

    Every non-dict shape is covered, not just the string: `or {}` falls through
    for each of them identically, so a guard written against `str` alone would
    leave the same hole open.
    """
    _make_target(tmp_path)
    tr = tmp_path / "agent-transcript.jsonl"
    tr.write_text("\n".join([
        _handback_line(REAL_REPORT),
        _malformed_handback_line(bad_input),
    ]) + "\n", encoding="utf-8")

    r = _subagent_stop(tmp_path, session, str(tr))
    assert r.returncode == 0, "the hook must still exit 0 even when this crashes"

    rec = _record_for(session)
    assert rec is not None, (
        "a real, earlier VERIFIED handback was dropped because an unrelated "
        "later tool_use block with a malformed `input` field crashed the scan "
        f"before it reached the real one. stderr: {r.stderr!r}"
    )
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


@pytest.mark.parametrize("bad_input", BAD_INPUTS)
def test_a_malformed_block_does_not_hide_a_good_one_in_the_same_entry(
    tmp_path, session, bad_input
):
    """The block walk is reversed too, so a malformed trailing block sits
    between the reader and the real handback inside a single message.

    This is the case that separates a real type guard from the backstop above
    it. The backstop drops the whole entry, good blocks and all; only the guard
    keeps scanning far enough to reach this one.
    """
    _make_target(tmp_path)
    tr = tmp_path / "agent-transcript.jsonl"
    tr.write_text(json.dumps({"message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "t1", "name": "SubagentHandback",
         "input": {"message": REAL_REPORT}},
        {"type": "tool_use", "id": "t2", "name": "SubagentHandback",
         "input": bad_input},
    ]}}) + "\n", encoding="utf-8")

    r = _subagent_stop(tmp_path, session, str(tr))
    assert r.returncode == 0

    rec = _record_for(session)
    assert rec is not None, f"the good block beside the bad one was lost. stderr: {r.stderr!r}"
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


class _RaisingEntry(dict):
    """An entry shape no isinstance guard anticipates.

    With every JSON-expressible shape now guarded, this is the only way left to
    build the case the guards exist to survive: an entry that blows up mid-walk.
    It stands in for whatever the next transcript format change turns out to be.
    """

    def get(self, *_args, **_kwargs):
        raise RuntimeError("shape drift nobody guarded")


def _json_shim(vr, explode_on):
    real = vr.json.loads

    class _Shim:
        dumps = staticmethod(vr.json.dumps)

        @staticmethod
        def loads(line):
            return _RaisingEntry() if line.strip() == explode_on else real(line)

    return _Shim


def test_an_entry_that_raises_costs_only_that_entry(tmp_path, monkeypatch):
    """The backstop. An unreadable entry must not end the backwards walk,
    because everything it would cost sits earlier in the file than it does."""
    vr = _hook_module()
    monkeypatch.setattr(vr, "json", _json_shim(vr, "@@EXPLODE@@"))

    report, unreadable = vr._scan_for_handback([_handback_line(REAL_REPORT), "@@EXPLODE@@"])

    assert report == REAL_REPORT, "an unreadable later entry swallowed the real report"
    assert unreadable == ["RuntimeError: shape drift nobody guarded"]


def test_an_all_malformed_transcript_is_distinguishable_from_an_empty_one(
    tmp_path, monkeypatch, capsys
):
    """"Nothing was reported" and "the report was unreadable" are different
    states. Returning the same silent empty string for both is the failure this
    whole record exists to rule out, so the second one says so on stderr."""
    vr = _hook_module()
    monkeypatch.setattr(vr, "json", _json_shim(vr, "@@EXPLODE@@"))
    tr = tmp_path / "agent-transcript.jsonl"
    tr.write_text("@@EXPLODE@@\n", encoding="utf-8")

    assert vr._handback_report(str(tr)) == ""
    err = capsys.readouterr().err
    assert "1 unreadable transcript entry" in err, err
    assert "RuntimeError: shape drift nobody guarded" in err, err

    # A transcript that genuinely holds no handback stays quiet.
    quiet = tmp_path / "quiet.jsonl"
    quiet.write_text(json.dumps({"message": {"role": "assistant", "content": [
        {"type": "text", "text": "VERIFIED: forged.py"}]}}) + "\n", encoding="utf-8")
    assert vr._handback_report(str(quiet)) == ""
    assert capsys.readouterr().err == ""


# --------------------------------------------------------------------------
# The other exception site: a line that never parses as JSON at all.
# --------------------------------------------------------------------------


def _chat_line(text):
    """Plain assistant text, which is most of what a transcript holds."""
    return json.dumps({"message": {"role": "assistant",
                                   "content": [{"type": "text", "text": text}]}})


#: A line that once held a real handback and no longer parses. Cut from the
#: right, so it still opens with `{` and still names SubagentHandback: nothing
#: in the text separates it from the fragment a tail seek leaves behind, which
#: is why position rather than content is what the scan is told.
CORRUPT_HANDBACK_LINE = (
    '{"message": {"role": "assistant", "content": [{"type": "tool_use", '
    '"name": "SubagentHandback", "input": {"message": "VERIFIED: real.py'
)


def test_an_unparseable_line_is_noted_not_swallowed():
    """Property 8 on the json.loads path.

    Before the fix this returned ('', []): a line that visibly once held a
    VERIFIED report left no trace at all, so the caller could not tell it from
    a transcript that never held a handback.
    """
    vr = _hook_module()
    report, unreadable = vr._scan_for_handback([CORRUPT_HANDBACK_LINE])

    assert report == ""
    assert len(unreadable) == 1, f"the corrupt line left no note: {unreadable!r}"
    assert unreadable[0].startswith("JSONDecodeError:"), unreadable[0]


def test_a_corrupt_transcript_reads_differently_from_an_empty_one(tmp_path, session):
    """The whole point, at the surface a person actually sees.

    A corrupted transcript used to produce stderr identical byte for byte to a
    transcript that never called SubagentHandback, so the only advice on offer
    was "the usual cause is a backgrounded spawn", pointing away from the real
    cause.
    """
    _make_target(tmp_path)
    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text(CORRUPT_HANDBACK_LINE + "\n", encoding="utf-8")
    none = tmp_path / "none.jsonl"
    none.write_text(_chat_line("No action needed.") + "\n", encoding="utf-8")

    a = _subagent_stop(tmp_path, session, str(corrupt))
    b = _subagent_stop(tmp_path, session + "-none", str(none))

    assert a.returncode == 0 and b.returncode == 0
    assert "unreadable transcript entry" in a.stderr, a.stderr
    assert "unreadable" not in b.stderr, b.stderr
    assert a.stderr != b.stderr


def test_an_unparseable_line_does_not_hide_an_earlier_handback(tmp_path, session):
    """Property 4, on this exception site. The walk runs backwards, so a
    corrupt last line sits between the reader and the real report."""
    _make_target(tmp_path)
    tr = tmp_path / "agent-transcript.jsonl"
    tr.write_text(_handback_line(REAL_REPORT) + "\n" + CORRUPT_HANDBACK_LINE + "\n",
                  encoding="utf-8")

    r = _subagent_stop(tmp_path, session, str(tr))

    assert r.returncode == 0
    rec = _record_for(session)
    assert rec is not None, f"the real earlier handback was lost. stderr: {r.stderr!r}"
    assert rec["stamps"][0]["covers"] == ["clean-rag/cli/log_tail.py"]


def test_the_seek_fragment_is_exempt_only_where_the_seek_put_it():
    """Position is the whole discrimination, so pin all three cases.

    A note on the expected fragment would fire on every transcript over
    512 KiB. A missing note anywhere else is the swallow this file exists to
    close.
    """
    vr = _hook_module()
    good = _chat_line("ordinary")

    _, exempt = vr._scan_for_handback(
        [CORRUPT_HANDBACK_LINE, good], first_line_may_be_cut=True
    )
    assert exempt == [], "the fragment the seek left behind was reported as corruption"

    _, later = vr._scan_for_handback(
        [good, CORRUPT_HANDBACK_LINE], first_line_may_be_cut=True
    )
    assert len(later) == 1, "corruption past the first line was exempted too"

    _, unseeked = vr._scan_for_handback([CORRUPT_HANDBACK_LINE, good])
    assert len(unseeked) == 1, "a whole file read has no fragment, so nothing is exempt"


@pytest.mark.parametrize("with_handback", [True, False])
def test_a_healthy_large_transcript_stays_silent_at_every_cut(
    tmp_path, capsys, with_handback
):
    """Property 9. A diagnostic that fires on a normal run is noise, and noise
    is how the real signal gets ignored.

    Sweeping the window a byte at a time walks the seek through every position
    in the file, including the ones that cut a line in half, which is the only
    thing a healthy transcript does to provoke a parse failure. Both paths are
    swept: with a handback the scan returns from the tail, without one it falls
    through to the whole file retry.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    body = [_chat_line("before"), _chat_line("thinking out loud")]
    if with_handback:
        body.append(_handback_line(REAL_REPORT))
    body.append(_chat_line("after"))
    p.write_bytes(("\n".join(body) + "\n").encode("utf-8"))

    size = p.stat().st_size
    saved = vr._TAIL_BYTES
    try:
        for window in range(1, size + 2):
            vr._TAIL_BYTES = window
            got = vr._handback_report(str(p))
            err = capsys.readouterr().err
            assert err == "", f"window={window} of {size} complained about a healthy file: {err}"
            assert got == (REAL_REPORT if with_handback else "")
    finally:
        vr._TAIL_BYTES = saved


def test_a_broken_retry_never_calls_the_seek_fragment_corruption(
    tmp_path, monkeypatch, capsys
):
    """The exemption has to live in the scan, not be papered over by the retry.

    On the ordinary no-report path the whole file retry re-scans from byte 0
    and replaces the tail scan's findings, which hides whether the fragment
    was ever recorded. The retry is not guaranteed: a transcript another
    process is still writing is the normal reason it fails. The tail scan's
    list then survives and is what gets printed.

    The read failure itself is reported, and must be: the retry could not
    look above the window, so a handback up there would be lost. What must
    never appear is a corruption note, because the only line that failed to
    parse is the fragment the seek left behind.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_bytes(("\n".join(_chat_line(t) for t in ("before", "middle", "after"))
                   + "\n").encode("utf-8"))
    size = p.stat().st_size

    real_read_text = Path.read_text

    def unreadable_retry(self, *args, **kwargs):
        if self == p:
            raise OSError("transcript is being written by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable_retry)

    saved = vr._TAIL_BYTES
    try:
        for window in range(1, size):
            vr._TAIL_BYTES = window
            assert vr._handback_report(str(p)) == ""
            err = capsys.readouterr().err
            assert "unreadable transcript" not in err, \
                f"window={window} of {size} called a healthy file corrupt: {err}"
            assert "could not read" in err, \
                f"window={window} of {size} swallowed the failed retry: {err}"
    finally:
        vr._TAIL_BYTES = saved
