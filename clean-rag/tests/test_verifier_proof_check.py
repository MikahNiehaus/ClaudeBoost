"""
The VERIFIED stamp must carry execution behind it.

bad-cop.md:879 and good-cop.md:493 both say VERIFIED is an execution claim, not
a review claim, and that the command and its actual output must appear before
that line. bad-cop.md names "I verified by inspection" as not qualifying.

None of it was enforced. verifier-record.py called record_verifier
unconditionally, record_verifier built the stamp from one regex on the marker
line, and check_file_verified then returned True. A report reading only
"VERIFIED: foo.py" was recorded identically to a fully evidenced one.

Two properties these tests exist to hold:

1. A VERIFIED with no execution anywhere in the report records nothing, so the
   files stay unverified.
2. The check is generous. It fires only when the report contains nothing
   resembling execution, because a false positive silently discards a real
   review, which is worse than letting a thin one through.

And one that is easy to get wrong: a rejected stamp must be ABSENT, not
recorded with an empty file list. verifier-gate.py's loop_stage reads a bad-cop
stamp with no covers as STAGE_BUGS_FOUND, so recording an empty one would say
"bad-cop found real bugs" instead of "nothing has been verified".
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
RECORD = HOOKS / "verifier-record.py"

SESSION = "proof-check-session"


def _load(filename: str, module_name: str):
    """Load a hyphenated hook file as a module."""
    spec = importlib.util.spec_from_file_location(module_name, HOOKS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load("verifier-record.py", "verifier_record_under_test")
gate = _load("verifier-gate.py", "verifier_gate_under_test")


def payload(report: str, agent: str = "bad-cop") -> dict:
    return {
        "tool_name": "Task",
        "session_id": SESSION,
        "tool_input": {"subagent_type": agent, "prompt": "review the diff"},
        "tool_response": [{"type": "text", "text": report}],
    }


ENV_ALLOWLIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
    "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PYTHONHOME", "PYTHONPATH",
    # Without this the hook writes its stamps into the real
    # clean-rag/state/verifier, since verifier_state._clean_rag_home() falls
    # back to the package directory when it is unset.
    "CLEAN_RAG_HOME",
}


@pytest.fixture(autouse=True)
def isolated_state_home(tmp_path, monkeypatch):
    """Point CLEAN_RAG_HOME at a scratch tree for the whole module.

    Same convention as test_verifier_gate_nits_routing.py uses for this module.
    run_hook passes it through the allowlist, so the subprocess inherits the
    scratch tree rather than falling back to the real one.
    """
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    return tmp_path


def run_hook(report: str, agent: str = "bad-cop", env_extra: dict | None = None):
    """Run the hook as a real subprocess with a DECLARED environment.

    Not the inherited one. A hook that passes because of what happens to sit in
    the developer's shell is an undeclared dependency, and this repo has already
    paid for that once.
    """
    import os
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_ALLOWLIST}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(RECORD)],
        input=json.dumps(payload(report, agent)),
        text=True, capture_output=True, timeout=120, env=env,
    )


def _run_raw(raw_stdin: str):
    """Same declared environment, but an arbitrary stdin body rather than a
    well formed payload."""
    import os
    env = {k: v for k, v in os.environ.items() if k.upper() in ENV_ALLOWLIST}
    return subprocess.run(
        [sys.executable, str(RECORD)], input=raw_stdin,
        text=True, capture_output=True, timeout=120, env=env,
    )


BARE = "VERIFIED: foo.py"

EVIDENCED = """
[High] off by one in the retry loop - foo.py:42
Evidence: for i in range(1, n):
Test: test_retry_covers_first_attempt

I ran the suite:

```
$ python -m pytest tests/test_foo.py -q
3 passed in 0.11s
```

VERIFIED: foo.py
"""


class TestTheGapItself:

    def test_bare_verified_has_no_execution_proof(self):
        assert mod._has_execution_proof(BARE) is False

    def test_bare_verified_is_not_recorded(self):
        r = run_hook(BARE)
        assert r.returncode == 0, "the hook must never block"
        assert "VERIFIED stamp not recorded" in r.stderr

    def test_the_nudge_names_the_agent_and_the_way_out(self):
        r = run_hook(BARE)
        assert "bad-cop" in r.stderr
        assert "CLEAN_RAG_VERIFIER_PROOF_CHECK=off" in r.stderr

    @pytest.mark.parametrize("phrase", [
        "I reviewed the code and found no issues.\n\nVERIFIED: foo.py",
        "The code looks correct to me.\n\nVERIFIED: foo.py",
        "I verified by inspection.\n\nVERIFIED: foo.py",
        "No failing tests found.\n\nVERIFIED: foo.py",
    ])
    def test_the_phrasings_bad_cop_md_rejects_by_name_are_rejected(self, phrase):
        assert mod._has_execution_proof(phrase) is False

    @pytest.mark.parametrize("prose", [
        # Pasted output is line shaped; prose about output is sentence shaped.
        # Both of these embed a runner's vocabulary mid sentence, which is what
        # separates them from the real thing.
        "OK, so I found no issues after reading the diff.",
        "The man page says a non zero exit code=1 means invalid arguments.",
        "OK then. The retry loop looks right to me.",
        "Callers should check the exit status before continuing.",
    ])
    def test_runner_vocabulary_inside_a_sentence_is_not_execution_proof(self, prose):
        assert mod._has_execution_proof(f"{prose}\n\nVERIFIED: foo.py") is False


class TestItDoesNotEatRealReviews:
    """A false positive discards a real review. These are the guard on that."""

    def test_a_fenced_output_block_counts(self):
        assert mod._has_execution_proof(EVIDENCED) is True

    def test_an_evidenced_report_is_recorded_silently(self):
        r = run_hook(EVIDENCED)
        assert r.returncode == 0
        assert "not recorded" not in r.stderr

    @pytest.mark.parametrize("body", [
        "$ pytest -q\n3 passed",                       # shown command
        "12 passed, 1 failed",                          # pytest summary
        "Ran 14 tests in 0.3s",                         # unittest
        "Traceback (most recent call last):",           # a real crash
        "OK",                                           # unittest success
        "exit code 1",                                  # a recorded exit
        "=== 3 passed in 0.2s ===",                     # pytest banner
        "PASS  src/foo.test.ts",                        # jest
    ])
    def test_output_pasted_without_fences_still_counts(self, body):
        assert mod._has_execution_proof(f"{body}\n\nVERIFIED: foo.py") is True

    @pytest.mark.parametrize("body", [
        # Real dotnet test output, captured from `dotnet test` on VSTest 18.0.1.
        "Passed!  - Failed:     0, Passed:     1, Skipped:     0, Total:     1",
        "OK (skipped=1)",                               # real unittest verdict
        "E       assert 4 == 5",                        # real pytest error line
        "t_assert.py:2: AssertionError",                # real pytest traceback tail
        "Tests:       1 failed, 2 passed, 3 total",     # jest
        "Set a breakpoint at foo.py:42 and read get_variables",  # mcp-debugger
        "Captured before.png and after.png",            # the eyes skill
    ])
    def test_the_other_real_proof_shapes_this_repo_uses_also_count(self, body):
        assert mod._has_execution_proof(f"{body}\n\nVERIFIED: foo.py") is True

    def test_good_cop_is_held_to_the_same_bar(self):
        r = run_hook(BARE, agent="good-cop")
        assert "VERIFIED stamp not recorded" in r.stderr
        assert "good-cop" in r.stderr


class TestOnlyTheVerifiedPathIsGated:
    """HANDOFF and NITS legitimately carry no file list, and that empty list is
    what drives the loop routing. Withholding those stamps breaks the handoff."""

    @pytest.mark.parametrize("marker", [
        "HANDOFF: 2 real findings, 1 new test added, run with pytest -q",
        "NITS: 1 nit finding, 0 new tests added, run with pytest -q",
    ])
    def test_non_verified_reports_are_untouched(self, marker):
        r = run_hook(f"I read the diff.\n\n{marker}")
        assert r.returncode == 0
        assert "not recorded" not in r.stderr

    @pytest.mark.parametrize("marker, expected_stage", [
        ("HANDOFF: 1 real finding, 0 new tests added", "bad-cop-found-bugs"),
        ("NITS: 1 nit finding, 0 new tests added", "bad-cop-found-nits-only"),
    ])
    def test_a_quoted_verified_line_does_not_change_where_the_loop_goes(
        self, marker, expected_stage, isolated_state_home
    ):
        """A report explaining this convention quotes a VERIFIED: line while
        closing on HANDOFF: or NITS:. Reading that quote as the verdict routes
        the loop off a stamp the agent never meant, so the routing is asserted
        by running loop_stage, not by reading the recorded file list."""
        report = (
            "[High] a report reading only\n\n"
            "VERIFIED: foo.py\n\n"
            "used to be recorded with no run behind it.\n\n"
            f"{marker}\n"
        )
        r = run_hook(report)
        assert r.returncode == 0
        assert "not recorded" not in r.stderr
        # isolated_state_home already points CLEAN_RAG_HOME at the same scratch
        # tree the subprocess wrote to, and _clean_rag_home() rereads it per call.
        assert gate.loop_stage(SESSION) == expected_stage


class TestFailOpen:

    def test_the_escape_hatch_disables_the_check(self):
        r = run_hook(BARE, env_extra={"CLEAN_RAG_VERIFIER_PROOF_CHECK": "off"})
        assert "not recorded" not in r.stderr

    def test_a_non_agent_payload_is_ignored(self):
        r = _run_raw(json.dumps({"tool_name": "Bash"}))
        assert r.returncode == 0
        assert r.stderr.strip() == ""

    def test_malformed_input_never_blocks(self):
        for raw in ("", "not json", "null", "[1,2,3]", '"a string"'):
            r = _run_raw(raw)
            assert r.returncode == 0, f"blocked on {raw!r}"
