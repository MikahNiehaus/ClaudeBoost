"""Adversarial follow-up on test_verifier_proof_check.py.

Four real gaps found while reviewing verifier-record.py and its test file,
each reproduced here as a real failing test against the current code. These
are additive, they do not modify the reviewed files.

1. A HANDOFF or NITS report that quotes a VERIFIED: example line in prose,
   while having no execution evidence anywhere else, is entirely swallowed
   instead of recorded with empty covers. That breaks the requirement that
   only the VERIFIED path is gated.
2. test_verifier_proof_check.py's run_hook() declares an environment
   allowlist but omits CLEAN_RAG_HOME, so verifier_state falls back to the
   real clean-rag/state/verifier directory and every test run writes a real
   stamp there. clean-rag/tests/test_verifier_gate_nits_routing.py already
   establishes the sibling convention of isolating CLEAN_RAG_HOME to a
   tmp_path for the exact same module.
3. _has_execution_proof accepts prose that merely starts a sentence with
   "OK" or mentions an exit code in passing, neither of which is real
   execution evidence, and both directly resemble the phrasings bad-cop.md
   names as insufficient ("I verified by inspection" style claims).
4. _has_execution_proof misses real evidenced report shapes: a dotnet test
   summary line, an assertion diff with no runner summary line, mcp-debugger
   step-through evidence, and screenshot-only evidence. All four are real
   proof styles this exact codebase's own CLAUDE.md names as legitimate
   (dotnet-trace, mcp-debugger get_variables, before/after screenshots).
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

BASE_ENV_KEYS = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PYTHONHOME", "PYTHONPATH",
}


def _load():
    spec = importlib.util.spec_from_file_location("verifier_record_adversarial", RECORD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def payload(report: str, agent: str = "bad-cop", session: str = "adversarial-session") -> dict:
    return {
        "tool_name": "Task",
        "session_id": session,
        "tool_input": {"subagent_type": agent, "prompt": "review the diff"},
        "tool_response": [{"type": "text", "text": report}],
    }


def run_hook(report: str, agent: str = "bad-cop", session: str = "adversarial-session",
             clean_rag_home: str | None = None):
    env = {k: v for k, v in os.environ.items() if k.upper() in BASE_ENV_KEYS}
    if clean_rag_home is not None:
        env["CLEAN_RAG_HOME"] = clean_rag_home
    return subprocess.run(
        [sys.executable, str(RECORD)],
        input=json.dumps(payload(report, agent, session)),
        text=True, capture_output=True, timeout=120, env=env,
    )


class TestHandoffSwallowedByVerifiedProse:
    """Finding 1: a real HANDOFF report is silently dropped instead of
    recorded, purely because it quotes a VERIFIED: example line in prose
    while having no execution proof of its own to show yet."""

    REPORT = (
        "[High] proof check regex only looks at known phrasings, not a real\n"
        "case like\n\n"
        "VERIFIED: foo.py\n\n"
        "which is what a report used to produce before this fix landed -\n"
        "verifier-record.py:166\n"
        "Evidence: record_verifier used to be called unconditionally\n"
        "Test: read the diff, no run yet\n\n"
        "HANDOFF: 1 real finding, 0 new tests added, run with pytest -q\n"
    )

    def test_handoff_report_is_recorded_not_swallowed(self, tmp_path):
        r = run_hook(self.REPORT, session="handoff-swallow-fixture",
                     clean_rag_home=str(tmp_path))
        assert r.returncode == 0
        assert "not recorded" not in r.stderr, (
            "a HANDOFF report must record with empty covers regardless of "
            "prose elsewhere in the body; instead it was swallowed entirely: "
            f"{r.stderr!r}"
        )


class TestEnvironmentIsolation:
    """Finding 2: running test_verifier_proof_check.py wrote real stamps into
    the real clean-rag/state/verifier. verifier_state._clean_rag_home() falls
    back to the package directory whenever CLEAN_RAG_HOME is unset, and that
    file's subprocess env allowlist did not carry it, so every run accumulated
    stamps in production state.

    Asserted end to end: run that test file the way CI does, with
    CLEAN_RAG_HOME scrubbed from the child environment, and require the real
    state directory to be untouched. Reproducing its env-building code here
    instead would pin the implementation rather than the contract, and would
    keep failing no matter how the isolation was done."""

    REAL_STATE_DIR = HOOKS.parent / "state" / "verifier"
    SIBLING = Path(__file__).resolve().parent / "test_verifier_proof_check.py"

    def _snapshot(self) -> set[str]:
        if not self.REAL_STATE_DIR.exists():
            return set()
        return {p.name for p in self.REAL_STATE_DIR.iterdir()}

    def test_running_the_sibling_file_does_not_touch_real_production_state(self):
        env = {k: v for k, v in os.environ.items() if k.upper() in BASE_ENV_KEYS}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        assert "CLEAN_RAG_HOME" not in env, "the child env must not inherit the isolation"

        before = self._snapshot()
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(self.SIBLING), "-q"],
            text=True, capture_output=True, timeout=600, env=env,
            cwd=str(HOOKS.parent.parent),
        )
        after = self._snapshot()

        assert r.returncode == 0, f"the sibling suite must pass:\n{r.stdout}\n{r.stderr}"
        assert after == before, (
            "running test_verifier_proof_check.py wrote into the real "
            f"production state directory ({self.REAL_STATE_DIR}): "
            f"{sorted(after - before)}"
        )


class TestExecutionSignalFalsePositives:
    """Finding 3: prose that merely starts a sentence with the word OK, or
    mentions an exit code in passing, is treated as execution proof. Neither
    ran anything. This is the same class of unearned claim bad-cop.md names
    by example ("I verified by inspection") and is supposed to reject."""

    def test_ok_as_a_sentence_opener_is_not_execution_proof(self):
        report = "OK, so bad-cop found no issues after reading the diff.\n\nVERIFIED: foo.py"
        assert mod._has_execution_proof(report) is False, (
            "an 'OK' interjection at the start of a sentence is not a real "
            "unittest OK, and must not count as execution proof"
        )

    def test_exit_code_mentioned_in_documentation_prose_is_not_execution_proof(self):
        report = (
            "The man page says a non zero exit code=1 means invalid arguments.\n\n"
            "VERIFIED: foo.py"
        )
        assert mod._has_execution_proof(report) is False, (
            "quoting what an exit code means is not the same as showing one "
            "from a real run"
        )


class TestExecutionSignalFalseNegatives:
    """Finding 4: real evidenced report shapes that this codebase's own
    CLAUDE.md names as legitimate proof (dotnet test runs, mcp-debugger
    step-through, before/after screenshots) are not recognized as execution
    proof, so a genuinely verified pass gets no stamp."""

    def test_dotnet_test_summary_counts(self):
        report = "Passed!  - Failed: 0, Passed: 7, Skipped: 0, Total: 7\n\nVERIFIED: foo.py"
        assert mod._has_execution_proof(report) is True

    def test_assertion_diff_with_no_summary_line_counts(self):
        report = "AssertionError: assert 4 == 5\n +4\n -5\n\nVERIFIED: foo.py"
        assert mod._has_execution_proof(report) is True

    def test_mcp_debugger_step_through_evidence_counts(self):
        report = (
            "Set a breakpoint at foo.py:42, stepped through, get_variables "
            "showed balance = -5 confirming the negative balance bug.\n\n"
            "VERIFIED: foo.py"
        )
        assert mod._has_execution_proof(report) is True

    def test_screenshot_only_evidence_counts(self):
        report = "Captured before.png and after.png, confirmed visually.\n\nVERIFIED: foo.py"
        assert mod._has_execution_proof(report) is True
