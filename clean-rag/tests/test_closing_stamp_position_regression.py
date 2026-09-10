"""Adversarial re-check on the closing_stamp() rewrite in verifier_state.py.

closing_stamp() replaced a precedence based rule (a real VERIFIED: or HANDOFF:
line anywhere beat a quoted NITS: line anywhere) with a position based one
(whichever of the three markers starts the LAST matching line wins). That
correctly fixes the case the rewrite's own docstring names: a report that
closes on NITS: after quoting VERIFIED: or HANDOFF: earlier, while explaining
the convention.

It introduces the opposite failure, never tested anywhere in this repo: a
report that closes on a real VERIFIED: or HANDOFF: line and then adds a
trailing note, footnote, or convention recap afterward -- an entirely ordinary
thing for a report *about this very loop* to do, which is exactly what this
closing re-check's own review scope is. If that trailing text contains a line
starting with "NITS:", the real close is silently overridden.

Both tests below are reproduced end to end through the real verifier-record.py
subprocess and verifier-gate.py's loop_stage, per the review instructions
("verify by running loop_stage, not by reading it"), not just unit-level
against closing_stamp().
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


vs = _load("verifier_state.py", "vs_regression_under_test")
gate = _load("verifier-gate.py", "gate_regression_under_test")


def payload(report: str, agent: str, session: str) -> dict:
    return {
        "tool_name": "Task",
        "session_id": session,
        "tool_input": {"subagent_type": agent, "prompt": "review the diff"},
        "tool_response": [{"type": "text", "text": report}],
    }


def run_hook(report: str, agent: str, session: str, clean_rag_home: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_ALLOWLIST}
    env["CLEAN_RAG_HOME"] = clean_rag_home
    return subprocess.run(
        [sys.executable, str(RECORD)],
        input=json.dumps(payload(report, agent, session)),
        text=True, capture_output=True, timeout=120, env=env,
    )


# A fully evidenced, genuinely clean bad-cop pass. Real command, real output,
# real VERIFIED: close naming the files -- then a trailing recap of the three
# closing conventions, exactly the kind of footnote a report *reviewing this
# loop's own code* would add.
CLEAN_PASS_WITH_TRAILING_RECAP = """I ran the real suite against verifier_state.py and verifier-record.py.

$ python -m pytest clean-rag/tests/test_verifier_proof_check.py -q
44 passed in 1.02s

VERIFIED: clean-rag/hooks/verifier_state.py, clean-rag/hooks/verifier-record.py

For the record, the three closing conventions this loop uses are:

VERIFIED: <files>
HANDOFF: <N> real findings, <M> new tests added, run with <command>
NITS: <N> nit findings, <M> new tests added, run with <command>
"""

# A real Critical finding, with evidence, closing on HANDOFF: -- then a
# footnote naming the other two conventions this report did not use, which
# happens to contain a line starting with "NITS:".
CRITICAL_HANDOFF_WITH_TRAILING_FOOTNOTE = """[Critical] SQL built by string concatenation - app.py:80
Evidence: query = "SELECT * FROM users WHERE id = " + user_id
Test: injected id="1 OR 1=1", got every row back
Failure: no parameterization at all

HANDOFF: 1 real finding, 1 new test added, run with pytest -q

Footnote: the other two closes this loop can end on are VERIFIED: <files> and
NITS: <N> nit findings, <M> new tests added, run with <command>, neither of
which applies here.
"""


class TestTrailingRecapDoesNotSwallowARealVerifiedClose:
    def test_closing_stamp_still_reads_verified(self):
        assert vs.closing_stamp(CLEAN_PASS_WITH_TRAILING_RECAP) == vs.VERIFIER_MARKER, (
            "a trailing recap of the convention overrode the real, evidenced "
            "VERIFIED: close"
        )

    def test_is_nits_only_pass_is_false(self):
        assert vs.is_nits_only_pass(CLEAN_PASS_WITH_TRAILING_RECAP) is False

    def test_record_verifier_keeps_the_covers_list(self, tmp_path, monkeypatch):
        r = run_hook(CLEAN_PASS_WITH_TRAILING_RECAP, "bad-cop", "recap-clean", str(tmp_path))
        assert r.returncode == 0
        assert "not recorded" not in r.stderr, r.stderr

        # _record_path resolves against CLEAN_RAG_HOME, which the subprocess got
        # but this process did not; without it the read lands in real state.
        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        record = json.loads(gate._record_path("recap-clean").read_text(encoding="utf-8"))
        stamp = record["stamps"][-1]
        assert stamp["covers"], (
            "the real VERIFIED: close was recorded with an empty file list, "
            f"stamp={stamp!r}"
        )
        assert stamp["nits_only"] is False

    def test_loop_stage_is_not_nits_only(self, tmp_path, monkeypatch):
        run_hook(CLEAN_PASS_WITH_TRAILING_RECAP, "bad-cop", "recap-clean-stage", str(tmp_path))
        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        stage = gate.loop_stage("recap-clean-stage")
        assert stage != gate.STAGE_NITS_ONLY, (
            "a genuinely clean, fully evidenced VERIFIED: pass was routed as "
            "if bad-cop had found nothing but nits"
        )


class TestTrailingFootnoteDoesNotSwallowARealHandoffClose:
    def test_closing_stamp_still_reads_handoff(self):
        assert vs.closing_stamp(CRITICAL_HANDOFF_WITH_TRAILING_FOOTNOTE) == vs.HANDOFF_MARKER, (
            "a trailing footnote naming the other conventions overrode a real "
            "Critical HANDOFF: close"
        )

    def test_is_nits_only_pass_is_false(self):
        assert vs.is_nits_only_pass(CRITICAL_HANDOFF_WITH_TRAILING_FOOTNOTE) is False, (
            "a real Critical finding closing on HANDOFF: was reclassified as "
            "nits_only because of a footnote line starting with NITS:"
        )

    def test_loop_stage_routes_to_good_cop_not_nits_only(self, tmp_path, monkeypatch):
        run_hook(
            CRITICAL_HANDOFF_WITH_TRAILING_FOOTNOTE, "bad-cop",
            "footnote-handoff-stage", str(tmp_path),
        )
        monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
        stage = gate.loop_stage("footnote-handoff-stage")
        assert stage == gate.STAGE_BUGS_FOUND, (
            f"a real Critical SQL injection finding was routed as {stage!r} "
            "instead of bad-cop-found-bugs, which tells the orchestrator to "
            "apply 'nit fixes' instead of spawning good-cop for a Critical bug"
        )


class TestTheCloseIsFoundInABlockNotByPosition:
    """The three shapes the block rule has to separate, none of which either
    "first match wins" or "last match wins" gets right on its own."""

    def test_fenced_stamp_does_not_override_the_real_close(self):
        """The fenced variant bad-cop confirmed against the position rule."""
        report = "Real review body.\n\nHANDOFF: 1 real finding\n\n```\nVERIFIED: foo.py\n```\n"
        assert vs.closing_stamp(report) == vs.HANDOFF_MARKER

    def test_quoted_stamp_before_the_real_close_does_not_win(self):
        """The failure the position rule was written to fix, still fixed."""
        report = (
            "I would emit this if it were clean:\n\n"
            "VERIFIED: <files>\n\n"
            "But it is not clean.\n\n"
            "HANDOFF: 1 real finding, 1 new test added, run with pytest -q\n"
        )
        assert vs.closing_stamp(report) == vs.HANDOFF_MARKER

    def test_a_real_nits_close_after_quoting_the_other_two_still_reads_as_nits(self):
        report = (
            "VERIFIED: is what I would emit if this were clean.\n"
            "HANDOFF: is for a Critical or High.\n\n"
            "NITS: 2 nit findings, 1 new test added, run with pytest -q\n"
        )
        assert vs.closing_stamp(report) == vs.NITS_MARKER
        assert vs.is_nits_only_pass(report) is True

    def test_a_stamp_that_closes_its_block_is_the_close(self):
        """The ordinary shape where the verdict line sits directly above the
        stamp with no blank line between them."""
        report = (
            "$ pytest -q\n3 passed\n\n"
            "VERDICT: safe to merge\n"
            "VERIFIED: a.py, b.py"
        )
        assert vs.closing_stamp(report) == vs.VERIFIER_MARKER

    def test_a_wrapper_line_after_the_stamp_does_not_lose_it(self):
        """Claude Code appends an agentId suffix to a spawned agent's report,
        which extract_covered_files already handles glued onto the stamp line."""
        report = "$ pytest -q\n3 passed\n\nVERIFIED: a.py\nagentId: xyz (use SendMessage)\n"
        assert vs.closing_stamp(report) == vs.VERIFIER_MARKER

    def test_an_unreadable_close_falls_back_to_the_good_cop_route(self):
        """Two markers in one block is a recap, so no close is found. That
        leaves covers empty, which routes to good-cop rather than ending the
        loop or downgrading a finding to polish."""
        report = "NITS: mentioned in passing\nHANDOFF: 1 real finding, 1 new test"
        assert vs.closing_stamp(report) == ""
        assert vs.is_nits_only_pass(report) is False
