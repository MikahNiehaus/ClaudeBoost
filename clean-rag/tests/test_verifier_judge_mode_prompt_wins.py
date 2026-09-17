"""A Mode B (/qa evidence judge) pass must never mint a Mode A code stamp.

is_evidence_judge_pass scanned the whole report for a VERIFIED/HANDOFF/NITS
shaped line and returned "Mode A" on the first hit, before it looked at the
spawn prompt. A Mode B judgement that explains the Mode A convention writes
such a line while explaining it, so the pass was recorded as a code review
stamp naming files nobody opened. Mode B looks at a finished QA session's
artifacts and never opens a diff, so there is nothing behind that stamp.

The spawn prompt is the routing fact: bad-cop.md:28 says Mode B is entered by
an explicit `MODE: evidence-judge` marker in the prompt, and the orchestrator
writes it. The report is the agent's own prose and quotes whatever it discusses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))

import verifier_state as vs  # noqa: E402

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env(home: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}
    env["CLEAN_RAG_HOME"] = str(home)
    return env


JUDGE_PROMPT = """MODE: evidence-judge

A /qa session has finished and claims it verified this work.
"""

# A realistic Mode B report: real pasted output, a closing FULLY VERIFIED, and
# the Mode A convention quoted once while explaining what the QA report got
# wrong.
JUDGE_REPORT_QUOTING_MODE_A = """\
# QA evidence judgement

```
$ python -m pytest tests/ -q
14 passed in 2.11s
```

A note on convention, since the report I judged got this wrong: a Mode A diff
review closes with a line of the form

VERIFIED: clean-rag/hooks/foo.py, clean-rag/hooks/bar.py

naming the files it reviewed. Mode B closes on FULLY VERIFIED: instead and
names no files, because there was no diff.

FULLY VERIFIED: 3 clauses, all evidenced
"""


def test_the_prompt_marker_decides_the_mode():
    assert vs.is_evidence_judge_pass(JUDGE_PROMPT, JUDGE_REPORT_QUOTING_MODE_A) is True


def test_the_prompt_marker_is_read_per_line_not_as_a_substring():
    """Bolded or headed, the way _normalize already reads a stamp line."""
    for prompt in ("**MODE: evidence-judge**", "# MODE: evidence-judge", "mode: EVIDENCE-JUDGE"):
        assert vs.is_evidence_judge_pass(prompt, "no stamp here") is True


def test_a_mode_b_pass_records_no_stamp(tmp_path):
    """End to end. The two files the report quoted must not appear anywhere in
    the record."""
    payload = {
        "tool_name": "Task",
        "session_id": "judge-mode",
        "tool_input": {"subagent_type": "bad-cop", "prompt": JUDGE_PROMPT},
        "tool_response": JUDGE_REPORT_QUOTING_MODE_A,
    }
    proc = subprocess.run(
        [sys.executable, str(HOOKS / "verifier-record.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=_hermetic_env(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr

    records = list((tmp_path / "state" / "verifier").glob("session-*.json"))
    assert records == [], (
        "a QA evidence judgement was recorded as a code review stamp: "
        + "; ".join(r.read_text(encoding="utf-8") for r in records)
    )


def test_a_mode_a_pass_with_no_prompt_marker_still_stamps():
    """The fix must not throw away a real diff review. With the prompt silent,
    the report's own closing line decides."""
    report = (
        "Ran the suite.\n\n"
        "    $ python -m pytest -q\n"
        "    14 passed in 0.42s\n\n"
        "VERIFIED: clean-rag/hooks/research-gate.py\n"
    )
    assert vs.is_evidence_judge_pass("Review this diff.", report) is False


def test_a_mode_a_report_quoting_the_judge_stamps_keeps_its_own():
    """A Mode A review OF this loop quotes both judge stamps. Its own close
    still wins, because the prompt never asked for Mode B."""
    report = (
        "The judge stamps are:\n"
        "FULLY VERIFIED: <clause count>\n"
        "TEST AGAIN: <N> gaps\n\n"
        "VERIFIED: clean-rag/hooks/verifier-record.py\n"
    )
    assert vs.is_evidence_judge_pass("", report) is False


def test_handoff_and_nits_are_mode_a():
    assert vs.is_evidence_judge_pass("", "HANDOFF: 1 real finding") is False
    assert vs.is_evidence_judge_pass("", "NITS: 2 nit findings") is False
