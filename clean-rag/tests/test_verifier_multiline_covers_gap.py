"""Adversarial finding from the closing re-check on the covers-scoping fix.

The fix correctly ties the covers list to the block closing_stamp actually
selected (see test_verifier_covers_scoping_gap.py). It does not fix a second,
narrower way the same list can come back empty on a genuinely clean, fully
evidenced VERIFIED close: when the marker sits alone on its own line and the
file list is wrapped to the next line of the SAME block, with no blank line
between them.

record_verifier calls:
    extract_covered_files("\\n".join(block), prefix=VERIFIER_MARKER)

extract_covered_files (research_state.py) scans line by line for the FIRST
line whose normalized text starts with the marker, then takes everything
after the colon on THAT SAME LINE ONLY, and returns immediately. It never
looks at the following line. A marker line with nothing after the colon
therefore returns [], even though the block closing_stamp identified is a
real VERIFIED close with real execution proof attached.

This reproduces end to end through the real verifier-record.py subprocess and
verifier-gate.py's loop_stage, per the review instructions:

  - The report has real pytest output before the close, so it clears the
    verifier-record.py proof-of-execution gate and IS recorded (not withheld
    the way a bare, unevidenced VERIFIED is).
  - It is recorded with covers == [], identical in shape to a HANDOFF or NITS
    stamp.
  - loop_stage then reads `agent == "bad-cop" and not covers` as
    STAGE_BUGS_FOUND, which tells the orchestrator "bad-cop ran and found
    real bugs, spawn good-cop NOW" -- for a pass that found nothing and
    closed clean.
  - Separately, check_file_verified for either file returns False forever,
    since file_in_scope against an empty covers list never matches. The files
    stay "unverified" on every subsequent Stop even though they were reviewed
    and the tests were run.

Not a regression introduced by the block-splitting rewrite under review --
extract_covered_files' single-line assumption is unchanged and pre-dates it,
and the old code (which called extract_covered_files on the whole report
instead of the closing block) hits the exact same limitation. It is a real,
currently reachable gap in the mechanism this re-check was asked to verify,
on exactly the input shape the review scope named ("a file list spanning
more than one line inside the close block").
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
RECORD = HOOKS / "verifier-record.py"

ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PYTHONHOME", "PYTHONPATH",
}


def _load(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vs = _load("verifier_state.py", "vs_multiline_gap")
gate = _load("verifier-gate.py", "gate_multiline_gap")


def payload(report: str, agent: str, session: str) -> dict:
    return {
        "tool_name": "Task",
        "session_id": session,
        "tool_input": {"subagent_type": agent, "prompt": "review the diff"},
        "tool_response": [{"type": "text", "text": report}],
    }


def run_hook(report: str, agent: str, session: str, clean_rag_home: str):
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_ALLOWLIST}
    env["CLEAN_RAG_HOME"] = clean_rag_home
    return subprocess.run(
        [sys.executable, str(RECORD)],
        input=json.dumps(payload(report, agent, session)),
        text=True, capture_output=True, timeout=120, env=env,
    )


REAL_CLEAN_PASS_WITH_WRAPPED_FILE_LIST = (
    "I reviewed foo.py and bar.py.\n\n"
    "$ python -m pytest tests/test_foo.py -q\n"
    "5 passed in 0.20s\n\n"
    "VERIFIED:\n"
    "foo.py, bar.py\n"
)


class TestWrappedFileListOnACleanVerifiedClose:
    def test_closing_stamp_still_reads_the_close_as_verified(self):
        # closing_stamp itself gets this right: the block's only marker line
        # is the first, so the close is identified correctly.
        assert vs.closing_stamp(REAL_CLEAN_PASS_WITH_WRAPPED_FILE_LIST) == vs.VERIFIER_MARKER

    def test_the_recorded_covers_list_should_not_be_empty(self, tmp_path, monkeypatch):
        r = run_hook(
            REAL_CLEAN_PASS_WITH_WRAPPED_FILE_LIST, "bad-cop",
            "wrapped-file-list-fixture", str(tmp_path),
        )
        assert r.returncode == 0
        assert "not recorded" not in r.stderr, (
            "expected this to be recorded (real execution proof is present); "
            f"it was withheld instead: {r.stderr!r}"
        )

        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        record = json.loads(gate._record_path("wrapped-file-list-fixture").read_text(encoding="utf-8"))
        stamp = record["stamps"][-1]

        assert stamp["covers"] == ["foo.py", "bar.py"], (
            "a real, fully evidenced VERIFIED close recorded an empty covers "
            f"list because the file names were wrapped to the line below the "
            f"marker instead of the same line: stamp={stamp!r}"
        )

    def test_loop_stage_should_not_read_this_as_bad_cop_found_bugs(self, tmp_path, monkeypatch):
        run_hook(
            REAL_CLEAN_PASS_WITH_WRAPPED_FILE_LIST, "bad-cop",
            "wrapped-file-list-stage", str(tmp_path),
        )
        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        stage = gate.loop_stage("wrapped-file-list-stage")
        assert stage != gate.STAGE_BUGS_FOUND, (
            "a genuinely clean bad-cop pass, with real pytest output and a "
            "real VERIFIED close, was routed as bad-cop-found-bugs, which "
            "tells the orchestrator to spawn good-cop over a review that "
            "found nothing, purely because the file list was on the line "
            "below the marker instead of the same line"
        )
