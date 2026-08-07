"""Which agent completions become a code-review stamp in the verifier record.

bad-cop runs in two modes. Mode A reviews a code diff and stamps `VERIFIED:` or
`HANDOFF:`; verifier-gate.py routes its block message off those. Mode B judges a
finished `/qa` session's evidence and stamps `FULLY VERIFIED:` or `TEST AGAIN:`,
having never looked at a diff or a file.

Recording a Mode B pass makes the gate announce "bad-cop ran and found real bugs
— spawn good-cop NOW" about code nobody reviewed, so a Mode B pass is not
recorded at all and Mode A behaves exactly as it did before Mode B existed.

These drive the real hook: the payload goes through verifier-record.py's main()
on stdin, and the routing comes back out of verifier-gate.py's loop_stage().

Run: python -m pytest tests/test_verifier_record_stamps.py -v
"""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import verifier_state  # noqa: E402
from verifier_state import is_evidence_judge_pass  # noqa: E402

SESSION = "verifier-record-stamps-session"

MODE_A_HANDOFF_REPORT = """[High] Off by one in the retry counter — retry.py:42
HANDOFF: 1 real finding, 2 new tests added, run with python -m pytest tests/
"""

MODE_A_CLEAN_REPORT = """Ran the suite, everything green.

VERIFIED: clean-rag/hooks/research-gate.py
"""

MODE_B_JUDGE_REPORT = """| 1 | "the qa Skill to properly walk through everything" | plan.md | PROVEN |

FULLY VERIFIED: 9 clauses, all proven — screenshots/proof-2026-08-05, debug-proof
"""

MODE_B_TEST_AGAIN_REPORT = """[High] TC-004 has no persisted value
Requirement: "you point to proof with it"
Missing: no debug json for the save path
Retest: breakpoint OrderService.Save, capture TotalAmount with mcp-debugger

TEST AGAIN: 1 gap
"""

JUDGE_SPAWN_PROMPT = """MODE: evidence-judge

A /qa session has finished and claims it verified this work.
"""

GOOD_COP_REPORT = """Fix: parameterized the query.

VERIFIED: clean-rag/server/app.py
"""


def _load_hook(filename: str, module_name: str):
    """Load a hyphenated hook file as a module."""
    spec = importlib.util.spec_from_file_location(module_name, HOOKS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verifier_record = _load_hook("verifier-record.py", "verifier_record_under_test")
verifier_gate = _load_hook("verifier-gate.py", "verifier_gate_under_test")


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the record at a temp CLEAN_RAG_HOME. _clean_rag_home() reads the env
    var on every call, so no reload is needed."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    yield tmp_path


def run_hook(agent_type: str, report: str, spawn_prompt: str = "", *, monkeypatch):
    """Fire verifier-record.py exactly as Claude Code does: a PostToolUse payload
    on stdin. Returns the hook's exit code."""
    payload = {
        "tool_name": "Task",
        "session_id": SESSION,
        "tool_input": {"subagent_type": agent_type, "prompt": spawn_prompt},
        "tool_response": report,
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return verifier_record.main()


def stamps():
    path = verifier_state._record_path(SESSION)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))["stamps"]


# ── the record only holds diff reviews ───────────────────────────────────────


def test_mode_a_handoff_is_recorded_with_no_covered_files(monkeypatch):
    assert run_hook("bad-cop", MODE_A_HANDOFF_REPORT, monkeypatch=monkeypatch) == 0
    assert [(s["agent"], s["covers"]) for s in stamps()] == [("bad-cop", [])]


def test_mode_a_clean_pass_records_the_files_it_covered(monkeypatch):
    assert run_hook("bad-cop", MODE_A_CLEAN_REPORT, monkeypatch=monkeypatch) == 0
    assert [(s["agent"], s["covers"]) for s in stamps()] == [
        ("bad-cop", ["clean-rag/hooks/research-gate.py"])
    ]


def test_good_cop_fix_is_recorded(monkeypatch):
    assert run_hook("good-cop", GOOD_COP_REPORT, monkeypatch=monkeypatch) == 0
    assert [(s["agent"], s["covers"]) for s in stamps()] == [
        ("good-cop", ["clean-rag/server/app.py"])
    ]


@pytest.mark.parametrize(
    "report",
    [MODE_B_JUDGE_REPORT, MODE_B_TEST_AGAIN_REPORT],
    ids=["fully-verified", "test-again"],
)
def test_evidence_judge_pass_writes_no_stamp(report, monkeypatch):
    assert run_hook("bad-cop", report, JUDGE_SPAWN_PROMPT, monkeypatch=monkeypatch) == 0
    assert stamps() == []


def test_evidence_judge_pass_writes_no_stamp_without_the_spawn_prompt(monkeypatch):
    """The routing marker lives in tool_input.prompt. If a payload ever arrives
    without it, the Mode B verdict in the report is still decisive."""
    assert run_hook("bad-cop", MODE_B_JUDGE_REPORT, monkeypatch=monkeypatch) == 0
    assert stamps() == []


def test_evidence_judge_pass_writes_no_stamp_when_it_reached_no_verdict(monkeypatch):
    """A judge that stopped before stamping still reviewed no diff, so the spawn
    marker alone has to keep it out of the record."""
    report = "Opened the artifacts. TC-004 has no debug json and I ran out of room."
    assert run_hook("bad-cop", report, JUDGE_SPAWN_PROMPT, monkeypatch=monkeypatch) == 0
    assert stamps() == []


# ── the gate routing that the corrupted state used to break ──────────────────


def test_evidence_judge_pass_leaves_the_gate_at_its_starting_stage(monkeypatch):
    """A clean Mode B judge pass used to be recorded as ('bad-cop', []), which is
    the gate's "bad-cop found real bugs — spawn good-cop NOW" stage."""
    run_hook("bad-cop", MODE_B_JUDGE_REPORT, JUDGE_SPAWN_PROMPT, monkeypatch=monkeypatch)
    assert verifier_gate.loop_stage(SESSION) == verifier_gate.STAGE_NO_VERIFIER


def test_evidence_judge_pass_does_not_displace_a_mode_a_handoff(monkeypatch):
    """A /qa judge round in the middle of a fix cycle must not move the gate off
    "spawn good-cop", because bad-cop's Mode A findings are still unfixed."""
    run_hook("bad-cop", MODE_A_HANDOFF_REPORT, monkeypatch=monkeypatch)
    run_hook("bad-cop", MODE_B_JUDGE_REPORT, JUDGE_SPAWN_PROMPT, monkeypatch=monkeypatch)
    assert verifier_gate.loop_stage(SESSION) == verifier_gate.STAGE_BUGS_FOUND


def test_mode_a_handoff_still_routes_to_good_cop(monkeypatch):
    run_hook("bad-cop", MODE_A_HANDOFF_REPORT, monkeypatch=monkeypatch)
    assert verifier_gate.loop_stage(SESSION) == verifier_gate.STAGE_BUGS_FOUND


def test_good_cop_stamp_routes_to_the_bad_cop_recheck(monkeypatch):
    run_hook("good-cop", GOOD_COP_REPORT, monkeypatch=monkeypatch)
    assert verifier_gate.loop_stage(SESSION) == verifier_gate.STAGE_FIX_STAMPED


def test_a_clean_mode_a_pass_verifies_the_file_it_named(monkeypatch, tmp_path):
    """The end the gate actually cares about: after a Mode A clean pass, the file
    it named passes check_file_verified."""
    reviewed = tmp_path / "research-gate.py"
    reviewed.write_text("# reviewed\n", encoding="utf-8")
    report = f"VERIFIED: {reviewed.as_posix()}\n"
    run_hook("bad-cop", report, monkeypatch=monkeypatch)

    ok, reason = verifier_state.check_file_verified(SESSION, str(reviewed))
    assert ok, reason
    assert "bad-cop" in reason


# ── the mode predicate itself ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "spawn_prompt, report, expected",
    [
        (JUDGE_SPAWN_PROMPT, MODE_B_JUDGE_REPORT, True),
        ("", MODE_B_JUDGE_REPORT, True),
        ("", MODE_B_TEST_AGAIN_REPORT, True),
        ("", "**FULLY VERIFIED:** 3 clauses, all proven — proof/", True),
        ("", MODE_A_HANDOFF_REPORT, False),
        ("", MODE_A_CLEAN_REPORT, False),
        ("", "", False),
        ("Review this diff.", "Nothing conclusive, no stamp emitted.", False),
    ],
)
def test_mode_detection(spawn_prompt, report, expected):
    assert is_evidence_judge_pass(spawn_prompt, report) is expected


def test_a_mode_a_report_that_quotes_the_judge_stamps_keeps_its_own_stamp():
    """A Mode A review of this very loop quotes "FULLY VERIFIED:" and "TEST
    AGAIN:". Its own VERIFIED: line decides the mode, so its stamp survives."""
    report = (
        "The judge stamps are:\n"
        "FULLY VERIFIED: <clause count>\n"
        "TEST AGAIN: <N> gaps\n\n"
        "VERIFIED: clean-rag/hooks/verifier-record.py\n"
    )
    assert is_evidence_judge_pass("", report) is False
