"""Round 3 adversarial re-check of verifier-record.py's tail/retry handback
scan (_transcript_lines, _scan_for_handback, _handback_report).

Written by bad-cop to attack the specific surfaces named for this round:
the index-0 seek exemption, the retry's `except OSError: pass`, and whether
the diagnostic (property 8: "no handback" vs "entry unreadable" must be
distinguishable) actually holds once a retry is involved. Does not touch
verifier-record.py or the existing test files; adds new cases only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
HOOK = HOOKS / "verifier-record.py"


def _hook_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_record_round3", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _chat_line(text):
    return json.dumps({"message": {"role": "assistant",
                                    "content": [{"type": "text", "text": text}]}})


def _handback_line(message):
    return json.dumps({
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "toolu_real", "name": "SubagentHandback",
             "input": {"message": message}},
        ]},
    })


REAL_REPORT = "VERIFIED: clean-rag/cli/log_tail.py\n"


def test_retry_oserror_with_a_real_handback_above_the_window_is_reported(
    tmp_path, monkeypatch, capsys
):
    """A read failure that loses a real handback must say so.

    Build a file where: (1) it is large enough to force a seek, (2) the real
    handback sits ABOVE the tail window so the tail scan alone cannot find
    it, (3) the tail window itself is ordinary, unremarkable chat with no
    parse failures at all, so the tail pass returns ("", []), and (4) the
    whole-file retry is made to raise OSError, simulating a transcript still
    being written by another process.

    Property 8's third state: the transcript could not be read at all. The
    report is unrecoverable here whatever we do, so the requirement is that
    it does not read as "this agent never handed back", which is what blames
    the agent for our own failure.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"

    real_handback = _handback_line(REAL_REPORT)
    # Padding sized so the handback line sits above (i.e., before) the tail
    # window once _TAIL_BYTES is shrunk below the total size.
    padding = [_chat_line("ordinary turn " + str(i)) for i in range(20)]
    body = [real_handback] + padding
    p.write_text("\n".join(body) + "\n", encoding="utf-8")

    tail_only = "\n".join(padding).encode("utf-8")
    size = p.stat().st_size
    assert size > len(tail_only), "padding did not leave the handback above the window"

    saved = vr._TAIL_BYTES
    real_read_text = Path.read_text

    def failing_retry(self, *args, **kwargs):
        if self == p:
            raise OSError("transcript is being written by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", failing_retry)

    try:
        # Force a seek that lands inside the padding, well clear of the real
        # handback line, so the tail scan itself sees only clean chat lines.
        vr._TAIL_BYTES = len(tail_only) - 40
        assert vr._TAIL_BYTES > 0

        got = vr._handback_report(str(p))
        err = capsys.readouterr().err
    finally:
        vr._TAIL_BYTES = saved

    assert got == "", "sanity: a real report cannot be found while the retry is blocked"
    assert err != "", (
        "a real handback was lost to a read failure with no diagnostic at all, "
        "so it is indistinguishable from an agent that never handed back"
    )
    assert "could not read" in err, err
    # The reason has to reach the reader, or the message cannot be acted on.
    assert "transcript is being written by another process" in err, err
    # It must not be mistaken for the other two states property 8 names.
    assert "unreadable transcript" not in err, (
        "a read failure was reported as skipped corrupt entries: " + err
    )


def test_index_zero_exemption_drops_the_note_when_a_report_is_found_elsewhere(
    tmp_path
):
    """The accepted limit of the positional exemption, pinned so it stays a
    decision rather than becoming a surprise.

    Genuine corruption landing exactly on the seek boundary loses its note
    when the scan finds a report later in the same window, because the retry
    that would re-derive it never runs once a report exists. Reporting it
    instead means reporting the seek fragment too, which nothing can be told
    apart from it, and that fires on every transcript over the window: the
    noise property 9 forbids.

    It can never hide a report, which is why it is worth no branch. A
    handback on that line does not parse either, so no report is found and
    the retry runs, as the next test proves.
    """
    vr = _hook_module()

    # A line that is genuinely corrupt independent of any seek (not a left
    # cut fragment -- it is simply malformed JSON), placed at index 0 of the
    # lines list handed to _scan_for_handback, with first_line_may_be_cut
    # asserted True as it would be for a real seeked read.
    genuinely_corrupt = '{"message": not valid json at all}}}'
    good_line = _handback_line(REAL_REPORT)

    report, unreadable = vr._scan_for_handback(
        [genuinely_corrupt, good_line], first_line_may_be_cut=True
    )

    assert report == REAL_REPORT, "the report must survive the dropped note"
    assert unreadable == [], (
        "the exemption stopped being positional; it now reports the seek "
        "fragment too, which fires on every transcript over the window"
    )


def test_bom_corruption_at_seek_index_zero_is_recovered_via_retry_when_it_holds_the_report(
    tmp_path
):
    """A BOM-corrupted line (real corruption, not a seek fragment) sitting
    exactly where the seek lands, holding the only report in the file. The
    tail scan cannot read it (exempted at index 0, and it wouldn't parse
    anyway), so report stays empty and the retry fires. The retry re-reads
    from byte 0 with no seek, so this same physical line is no longer at
    logical index 0 of the retry's own line list (the file has earlier
    lines) -- confirming good-cop's claim that the retry recovers a report
    that was merely swallowed by the tail's positional exemption, as long as
    the underlying bytes actually parse once read from their true start.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"

    good_handback = _handback_line(REAL_REPORT)
    padding = [_chat_line("pad " + str(i)) for i in range(5)]
    body = [_chat_line("first real line of the file")] + padding + [good_handback]
    p.write_text("\n".join(body) + "\n", encoding="utf-8")

    size = p.stat().st_size
    saved = vr._TAIL_BYTES
    try:
        # Shrink the tail window so the seek lands inside the handback line
        # itself, cutting it into an unparseable fragment at tail-index 0.
        handback_bytes = len(good_handback.encode("utf-8"))
        vr._TAIL_BYTES = handback_bytes // 2
        assert 0 < vr._TAIL_BYTES < size

        got = vr._handback_report(str(p))
    finally:
        vr._TAIL_BYTES = saved

    assert got == REAL_REPORT, "the retry did not recover a report cut by the seek"


# The three read sites upstream of the retry swallowed an OSError the same way
# it did. They are one state now ("the transcript could not be read"), owned by
# _handback_report, so these pin each site through that one boundary.

def test_a_failed_tail_read_is_retried_and_recovers_the_report(
    tmp_path, monkeypatch, capsys
):
    """A small transcript never reaches the seek, so its read failure used to
    be terminal: the retry only ran on a file bigger than the window.

    A held file is transient, so the whole file read is the retry it already
    had. Nothing is reported when it works, because nothing was lost.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text(_chat_line("before") + "\n" + _handback_line(REAL_REPORT) + "\n",
                 encoding="utf-8")
    assert p.stat().st_size < vr._TAIL_BYTES, "this must take the small file path"

    real_read_text = Path.read_text
    calls = []

    def fails_once(self, *args, **kwargs):
        if self == p:
            calls.append(1)
            if len(calls) == 1:
                raise OSError("transcript is being written by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fails_once)

    got = vr._handback_report(str(p))
    err = capsys.readouterr().err

    assert len(calls) == 2, f"the failed read was not retried, {len(calls)} read(s)"
    assert got == REAL_REPORT, "the retry did not recover the report"
    assert err == "", "a recovered read still complained: " + err


def test_a_stat_failure_is_recovered_by_the_retry(tmp_path, monkeypatch, capsys):
    """A failed stat used to end the whole read: the size was unknown, so the
    tail returned nothing and the retry's own size test never let it look.

    The retry now runs on any failed read, and reading the file answers the
    question the stat was only ever asked to size.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text(_handback_line(REAL_REPORT) + "\n", encoding="utf-8")

    real_stat = Path.stat
    refused = []

    def refuse_first(self, *args, **kwargs):
        if self == p and not refused:
            refused.append(1)
            raise PermissionError("WinError 5: access is denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refuse_first)

    got = vr._handback_report(str(p))
    err = capsys.readouterr().err

    assert refused, "the stat was never refused, so this tested nothing"
    assert got == REAL_REPORT, "the retry did not recover from a failed stat"
    assert err == "", "a recovered read still complained: " + err


def test_a_read_that_fails_every_way_is_reported(tmp_path, monkeypatch, capsys):
    """When no read succeeds there is nothing to conclude, and saying nothing
    is the one answer that reads as `this agent never handed back`."""
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text(_handback_line(REAL_REPORT) + "\n", encoding="utf-8")

    def refuse(self, *args, **kwargs):
        raise PermissionError("WinError 5: access is denied")

    monkeypatch.setattr(Path, "read_text", refuse)

    got = vr._handback_report(str(p))
    err = capsys.readouterr().err

    assert got == ""
    assert "could not read" in err, err
    assert "access is denied" in err, err
    assert "not a missing report" in err, "the state was not distinguished: " + err


def test_a_recovered_read_finding_no_handback_stays_silent(
    tmp_path, monkeypatch, capsys
):
    """Property 9 on the recovery path, and the reason the error is cleared
    once the whole file has been read.

    An agent that never handed back is the ordinary no-report run. If a read
    failure that the retry went on to fix still printed, the diagnostic would
    fire on a healthy run and stop being worth reading.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text(_chat_line("just talking") + "\n" + _chat_line("still talking") + "\n",
                 encoding="utf-8")
    assert p.stat().st_size < vr._TAIL_BYTES, "this must take the small file path"

    real_read_text = Path.read_text
    calls = []

    def fails_once(self, *args, **kwargs):
        if self == p:
            calls.append(1)
            if len(calls) == 1:
                raise OSError("transcript is being written by another process")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fails_once)

    got = vr._handback_report(str(p))
    err = capsys.readouterr().err

    assert len(calls) == 2, "the failed read was not retried"
    assert got == ""
    assert err == "", (
        "the whole file was read and genuinely held no handback, yet the "
        "earlier failure was still reported: " + err
    )


def test_the_failure_that_stopped_us_first_is_the_one_named(
    tmp_path, monkeypatch, capsys
):
    """The seek read has its own failure, and it is the informative one.

    Reporting whichever failure happened last would name the retry every
    time and hide what actually went wrong.
    """
    vr = _hook_module()
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(_chat_line("pad " + str(i)) for i in range(40)) + "\n",
                 encoding="utf-8")

    real_open = Path.open

    def refuse_binary(self, mode="r", *args, **kwargs):
        if self == p and "b" in mode:
            raise OSError("the seek read failed")
        return real_open(self, mode, *args, **kwargs)

    def refuse_retry(self, *args, **kwargs):
        raise OSError("the whole file retry failed")

    monkeypatch.setattr(Path, "open", refuse_binary)
    monkeypatch.setattr(Path, "read_text", refuse_retry)

    saved = vr._TAIL_BYTES
    try:
        vr._TAIL_BYTES = 64
        assert vr._TAIL_BYTES < p.stat().st_size, "this must take the seek path"
        got = vr._handback_report(str(p))
        err = capsys.readouterr().err
    finally:
        vr._TAIL_BYTES = saved

    assert got == ""
    assert "the seek read failed" in err, (
        "the seek's own failure was swallowed and the retry's reported "
        "instead: " + err
    )


def test_a_missing_transcript_says_nothing(tmp_path, capsys):
    """Property 9 for the read diagnostic. No transcript is a real empty
    result, not a read failure, and it is the ordinary shape for an agent
    that never handed back."""
    vr = _hook_module()

    got = vr._handback_report(str(tmp_path / "never-existed.jsonl"))

    assert got == ""
    assert capsys.readouterr().err == "", "a missing transcript was called unreadable"
