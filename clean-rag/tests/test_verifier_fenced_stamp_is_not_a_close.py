"""A stamp quoted inside pasted runner output must never be read as the close.

_blocks() split on blank lines with no knowledge of fences, and the comment
above it claimed no special case was needed: a stamp inside a fence "sits
between the two delimiter lines, so it is never its block's first or last
line". That holds only while the fence contains no blank line. pytest prints
one between the progress line and the summary, so an ordinary pasted run split
into two blocks, and a "VERIFIED: other.py" on the line after the blank opened
the second one. _closing_block accepted it, record_verifier read its file list,
and check_file_verified then returned True for a path nobody had opened, while
the files the report really reviewed got no stamp at all.

bad-cop.md instructs the agent to paste real output inside a fence, so this is
the ordinary report shape rather than a constructed one.

CommonMark 4.5 is the rule the fix follows: a fenced code block runs to a
closing fence of the same character, or to the end of the document, and a blank
line inside it is content.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


# A blank line inside the fence, exactly where pytest puts one.
QUOTED_IN_FENCE = """\
# Adversarial review

I read the diff, which touches auth.py and session.py.

```
$ python -m pytest tests/test_auth.py -q
....                                                      [100%]
4 passed in 0.31s

VERIFIED: unrelated/never_reviewed.py
```
"""


@pytest.mark.parametrize(
    "fence, closer",
    [
        ("```", "```"),
        ("~~~", "~~~"),
        ("````", "````"),
        ("```text", "```"),
        ("```", "`````"),
    ],
)
def test_a_stamp_inside_a_fence_never_closes_the_report(fence, closer):
    report = (
        "I read the diff.\n\n"
        f"{fence}\n"
        "$ python -m pytest -q\n"
        "4 passed\n"
        "\n"
        "VERIFIED: unrelated/never_reviewed.py\n"
        f"{closer}\n"
    )
    assert vs.closing_stamp(report) == "", (
        f"a quoted stamp inside a {fence!r} fence was read as the report's close"
    )


def test_the_quoted_path_is_never_recorded(tmp_path):
    """End to end through the real hook: nothing the fence named gets a stamp."""
    payload = {
        "tool_name": "Task",
        "session_id": "fenced-stamp",
        "tool_input": {"subagent_type": "bad-cop", "prompt": "Review the diff."},
        "tool_response": QUOTED_IN_FENCE,
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
    covers = [
        c
        for r in records
        for s in json.loads(r.read_text(encoding="utf-8")).get("stamps", [])
        for c in s.get("covers", [])
    ]
    assert covers == [], f"a path quoted inside pasted output was recorded: {covers}"


def test_a_real_close_after_a_fence_still_stamps(tmp_path):
    """The fence must not swallow the stamp that follows it. This is the shape
    bad-cop.md asks for: output pasted, then the closing line below it."""
    reviewed = tmp_path / "reviewed.py"
    reviewed.write_text("# reviewed\n", encoding="utf-8")
    report = (
        "Ran the suite.\n\n"
        "```\n"
        "$ python -m pytest -q\n"
        "\n"
        "14 passed in 0.42s\n"
        "```\n\n"
        f"VERIFIED: {reviewed.as_posix()}\n"
    )
    assert vs.closing_stamp(report) == vs.VERIFIER_MARKER

    payload = {
        "tool_name": "Task",
        "session_id": "fenced-stamp-ok",
        "tool_input": {"subagent_type": "bad-cop", "prompt": "Review the diff."},
        "tool_response": report,
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
    covers = [
        c
        for r in records
        for s in json.loads(r.read_text(encoding="utf-8")).get("stamps", [])
        for c in s.get("covers", [])
    ]
    assert covers == [reviewed.as_posix()], covers


def test_a_fence_line_carrying_an_info_string_does_not_close_the_fence():
    """CommonMark 4.5 lets only the opener carry an info string, so a
    ```` ```text ```` line inside a fence is content and the fence stays open.
    Treating it as a closer would end the region early and expose the rest of
    the pasted output, which is where the quoted stamp sits. Reachable whenever
    a report pastes a command that prints markdown."""
    report = (
        "Output:\n\n"
        "```\n"
        "$ cat NOTES.md\n"
        "```text\n"
        "4 passed\n"
        "\n"
        "VERIFIED: never_reviewed.py\n"
        "```\n"
    )
    assert vs.closing_stamp(report) == "", (
        "a fence line with an info string was treated as a closing fence, "
        "exposing the stamp quoted after it"
    )


def test_an_unclosed_fence_swallows_rather_than_exposes():
    """The deliberate fail direction. A fence with no closer runs to the end of
    the document (CommonMark 4.5), so a stamp after it is lost and the files
    keep reading as unverified, which keeps nudging. The other direction is
    silent."""
    report = "Output:\n\n```\n4 passed\n\nVERIFIED: never_reviewed.py\n"
    assert vs.closing_stamp(report) == ""
