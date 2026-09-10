"""Adversarial re-check on the closing_stamp() block rewrite, aimed at the one
gap good-cop named and deliberately left, and then called safe: covers is
still extracted from the WHOLE report text, not from the block closing_stamp
picked as the real close.

closing_stamp() correctly walks blocks last to first and finds the real
VERIFIED close even when an earlier block merely quotes or illustrates the
marker. record_verifier() then calls extract_covered_files(report, ...), and
that function (research_state.py) does its own independent top to bottom scan
for the FIRST line starting with the marker, with no idea which block
closing_stamp actually chose. When those two disagree about which block is
"the close", the covers list comes from the wrong one.

good-cop's stated defense is that this fails safe: the bogus path matches
nothing real, so the reviewed files just stay unverified. Both tests below
run the real subprocess end to end and show that defense does not hold:

  1. A quoted example line naming a real project file records THAT file as
     verified, even though the real close names a different file the report
     actually reviewed. The reviewed file is left unverified; an untouched
     file is marked verified instead.
  2. Quoting bad-cop.md's own documented closing template, exactly the kind
     of thing a report reviewing this very mechanism does (as this task's own
     review scope required), records the literal placeholder text "<file>,
     <file>" as the covers list. The real reviewed files are recorded nowhere,
     so the gate keeps nudging that they were never verified, forever, even
     though bad-cop's own report both reviewed them and ran real tests
     against them.

Neither report is contrived to defeat the rule. Both are ordinary shapes for
a report about this exact subsystem to take.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
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


vs = _load("verifier_state.py", "vs_covers_scoping_gap")


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


class TestQuotedExampleLineHijacksCoverage:
    """An earlier illustrative line naming a real project file steals the
    covers slot from the file the report actually reviewed and closed on."""

    REPORT = (
        "Before this fix, a report like\n\n"
        "VERIFIED: app.py\n\n"
        "used to be recorded with no run behind it, marking app.py reviewed "
        "when nobody looked at it. Here is the real review, on the actual "
        "file in scope for this change:\n\n"
        "$ python -m pytest clean_rag/tests/test_config.py -q\n"
        "5 passed in 0.20s\n\n"
        "VERIFIED: config.py\n"
    )

    def test_closing_stamp_itself_reads_the_real_close(self):
        assert vs.closing_stamp(self.REPORT) == vs.VERIFIER_MARKER

    def test_the_actually_reviewed_file_ends_up_verified_not_the_decoy(
        self, tmp_path, monkeypatch
    ):
        real_config = tmp_path / "config.py"
        real_app = tmp_path / "app.py"
        real_config.write_text("# config\n")
        real_app.write_text("# app\n")
        time.sleep(0.3)

        r = run_hook(self.REPORT, "bad-cop", "covers-hijack-fixture", str(tmp_path))
        assert r.returncode == 0
        assert "not recorded" not in r.stderr, r.stderr

        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        ok_config, _ = vs.check_file_verified("covers-hijack-fixture", str(real_config))
        ok_app, _ = vs.check_file_verified("covers-hijack-fixture", str(real_app))

        assert ok_config is True, (
            "config.py was the file the report actually reviewed and closed "
            "VERIFIED on, but it was not recorded as verified: covers came "
            "from the earlier quoted decoy line naming app.py instead"
        )
        assert ok_app is False, (
            "app.py was only named in a hypothetical illustrative example, "
            "never actually reviewed, but it was recorded as verified"
        )


class TestQuotingTheDocumentedTemplateDropsRealCoverage:
    """A report explaining bad-cop's own closing convention, exactly what a
    review of this subsystem does, quotes the fenced template with its
    literal <file>, <file> placeholder before the real close. That
    placeholder becomes the recorded covers list, and the files actually
    reviewed and run against are never recorded at all."""

    REPORT = (
        "For context, here is bad-cop's own closing convention as documented:\n\n"
        "```\n"
        "HANDOFF: <N> real findings, <M> new tests added, run with <command>\n"
        "```\n"
        "Use this only when at least one finding is Critical or High.\n\n"
        "```\n"
        "NITS: <N> nit findings, <M> new tests added, run with <command>\n"
        "```\n"
        "Use this when every finding is Nit severity. good-cop is not spawned.\n\n"
        "```\n"
        "VERIFIED: <file>, <file>\n"
        "```\n"
        "Use this when the findings list is empty.\n\n"
        "$ python -m pytest clean-rag/tests -k verifier -q\n"
        "77 passed in 9.87s\n\n"
        "Having reviewed the actual diff, I found nothing.\n\n"
        "VERIFIED: verifier_state.py, verifier-record.py\n"
    )

    def test_closing_stamp_itself_reads_the_real_close(self):
        assert vs.closing_stamp(self.REPORT) == vs.VERIFIER_MARKER

    def test_the_real_reviewed_files_end_up_verified(self, tmp_path, monkeypatch):
        real_vstate = tmp_path / "verifier_state.py"
        real_vstate.write_text("# x\n")
        time.sleep(0.3)

        r = run_hook(self.REPORT, "bad-cop", "template-quote-fixture", str(tmp_path))
        assert r.returncode == 0
        assert "not recorded" not in r.stderr, r.stderr

        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        ok, reason = vs.check_file_verified("template-quote-fixture", str(real_vstate))

        assert ok is True, (
            "verifier_state.py was actually reviewed, run against, and "
            f"closed on VERIFIED, but was not recorded as verified: {reason!r}. "
            "The recorded covers list came from the fenced template's literal "
            "<file>, <file> placeholder instead of the real close line."
        )


class TestWhitespaceOnlyLineStillSplitsBlocks:
    """Kill test for a hand mutation run against this exact code: changing
    _blocks' blank test from "the normalized line is falsy" to "the raw line
    is exactly empty" survived the entire existing 79 test suite, because
    none of them put a whitespace only line, as opposed to a truly empty one,
    between two blocks. The real code already gets this right; nothing
    committed proved it before this test."""

    def test_a_line_of_only_spaces_between_two_stamps_still_separates_them(self):
        report = "VERIFIED: foo.py\n \nHANDOFF: 1 real finding, 1 new test added\n"
        assert vs.closing_stamp(report) == vs.HANDOFF_MARKER, (
            "a line containing only spaces must count as a block boundary the "
            "same as a truly empty line, or the decoy VERIFIED: line above "
            "joins the same block as the real HANDOFF: close and the block "
            "is read as unreadable instead of a real close"
        )
