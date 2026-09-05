"""Routing for bad-cop's three closing lines: VERIFIED:, NITS:, HANDOFF:.

NITS: was added so a run whose findings are all Nit severity does not spawn
good-cop. The orchestrator applies those fixes itself and re-runs bad-cop for
the stamp.

The routing is easy to get wrong because NITS: and HANDOFF: both leave `covers`
empty. Before the nits_only flag, `loop_stage` had only the emptiness of
`covers` to go on, so a NITS: run was indistinguishable from a HANDOFF: run and
the gate asked for an Opus fix pass over polish. These tests pin the flag, the
three-way routing, and the behavior for stamps written before the flag existed.

The existing coverage for these two modules lives in tests/ at the repo root
(test_bad_cop_detection.py, test_verifier_gate_nudge_text.py,
test_verifier_record_stamps.py), not in this directory. None of it touches the
nits_only flag or the three-way routing, which is what this file is for.
"""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "clean-rag" / "hooks"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def state():
    sys.path.insert(0, str(HOOKS))
    return _load("_cr_verifier_state", HOOKS / "verifier_state.py")


@pytest.fixture(scope="module")
def gate():
    sys.path.insert(0, str(HOOKS))
    return _load("_cr_verifier_gate", HOOKS / "verifier-gate.py")


# --- is_nits_only_pass -----------------------------------------------------


def test_nits_line_is_recognized(state):
    report = "Some findings.\n\nNITS: 3 nit findings, 2 new tests added, run with pytest"
    assert state.is_nits_only_pass(report) is True


def test_verified_line_beats_a_quoted_nits_line(state):
    """A report that discusses the NITS convention and then stamps clean is a
    clean pass, not a nit only pass. Same precedence is_evidence_judge_pass uses."""
    report = (
        "I considered emitting NITS: but found nothing at all.\n"
        "VERIFIED: clean-rag/hooks/verifier_state.py"
    )
    assert state.is_nits_only_pass(report) is False


def test_handoff_line_beats_a_quoted_nits_line(state):
    report = "NITS: mentioned in passing\nHANDOFF: 1 real finding, 1 new test"
    assert state.is_nits_only_pass(report) is False


def test_report_with_no_closing_line_is_not_nits_only(state):
    assert state.is_nits_only_pass("just some prose, no stamp") is False


def test_empty_report_is_not_nits_only(state):
    assert state.is_nits_only_pass("") is False


def test_nits_report_is_not_mistaken_for_the_qa_evidence_judge(state):
    """A Mode A NITS: close must not be swallowed as a Mode B pass, or
    verifier-record.py drops the stamp and the gate never sees the run."""
    assert state.is_evidence_judge_pass("", "NITS: 2 nit findings") is False


# --- record_verifier writes the flag ---------------------------------------


def _write_stamps(gate, session_id, stamps):
    path = gate._record_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"session_id": session_id, "stamps": stamps}), encoding="utf-8"
    )
    return path


def test_record_verifier_stores_nits_only_true(state, gate, tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "nits-flag-true"
    state.record_verifier(session, "NITS: 2 nit findings", agent_type="bad-cop")
    record = json.loads(state._record_path(session).read_text(encoding="utf-8"))
    assert record["stamps"][-1]["nits_only"] is True
    assert record["stamps"][-1]["covers"] == []


def test_record_verifier_stores_nits_only_false_on_handoff(state, tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "nits-flag-false"
    state.record_verifier(session, "HANDOFF: 1 real finding", agent_type="bad-cop")
    record = json.loads(state._record_path(session).read_text(encoding="utf-8"))
    assert record["stamps"][-1]["nits_only"] is False


# --- loop_stage routing ----------------------------------------------------


def test_nits_only_stamp_routes_away_from_good_cop(gate, tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "route-nits"
    _write_stamps(gate, session, [{"agent": "bad-cop", "covers": [], "nits_only": True}])
    assert gate.loop_stage(session) == gate.STAGE_NITS_ONLY


def test_handoff_stamp_still_routes_to_good_cop(gate, tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "route-handoff"
    _write_stamps(gate, session, [{"agent": "bad-cop", "covers": [], "nits_only": False}])
    assert gate.loop_stage(session) == gate.STAGE_BUGS_FOUND


def test_stamp_written_before_the_flag_existed_routes_to_good_cop(gate, tmp_path, monkeypatch):
    """No nits_only key at all. Reads as False, which is the old behavior."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "route-legacy"
    _write_stamps(gate, session, [{"agent": "bad-cop", "covers": []}])
    assert gate.loop_stage(session) == gate.STAGE_BUGS_FOUND


def test_nits_flag_is_ignored_when_bad_cop_actually_stamped(gate, tmp_path, monkeypatch):
    """covers non empty means a real VERIFIED:. That wins over a stray flag."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "route-stamped"
    _write_stamps(
        gate, session, [{"agent": "bad-cop", "covers": ["a.py"], "nits_only": True}]
    )
    assert gate.loop_stage(session) == gate.STAGE_NO_VERIFIER


def test_good_cop_stamp_routes_to_the_recheck(gate, tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "route-fix"
    _write_stamps(gate, session, [{"agent": "good-cop", "covers": ["a.py"]}])
    assert gate.loop_stage(session) == gate.STAGE_FIX_STAMPED


def test_only_the_newest_stamp_decides_the_route(gate, tmp_path, monkeypatch):
    """A nit only round followed by a real handoff must route to good-cop, not
    stay on the nit route because an older stamp carried the flag."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = "route-newest"
    _write_stamps(
        gate,
        session,
        [
            {"agent": "bad-cop", "covers": [], "nits_only": True},
            {"agent": "bad-cop", "covers": [], "nits_only": False},
        ],
    )
    assert gate.loop_stage(session) == gate.STAGE_BUGS_FOUND


# --- the widened tuple -----------------------------------------------------


@pytest.mark.parametrize(
    "setup",
    ["missing", "corrupt", "empty"],
    ids=["no record file", "unparseable json", "stamps list empty"],
)
def test_every_early_return_is_a_three_tuple(gate, tmp_path, monkeypatch, setup):
    """_last_verifier_agent grew a third element. An early return still yielding
    two would raise ValueError inside loop_stage, on a Stop hook, on every turn."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    session = f"tuple-{setup}"
    if setup == "corrupt":
        path = gate._record_path(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
    elif setup == "empty":
        _write_stamps(gate, session, [])

    agent, covers, nits_only = gate._last_verifier_agent(session)
    assert (agent, covers, nits_only) == ("", [], False)
    assert gate.loop_stage(session) == gate.STAGE_NO_VERIFIER


# --- the nudge cap across rounds -------------------------------------------


def _set_block_count(gate, session_id, count):
    gate.BLOCK_DIR.mkdir(parents=True, exist_ok=True)
    (gate.BLOCK_DIR / f"{session_id}.count").write_text(str(count), encoding="utf-8")


def _read_block_count(gate, session_id):
    return int((gate.BLOCK_DIR / f"{session_id}.count").read_text(encoding="utf-8"))


@pytest.fixture
def run_stop(gate, tmp_path, monkeypatch, capsys):
    """Drive main() with the git, test-runner and stamp-lookup boundaries stubbed.

    Everything stubbed here is I/O main() does not own. The counter, the stage
    routing and the message it prints are the real code under test.
    """
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    monkeypatch.setattr(gate, "BLOCK_DIR", tmp_path / "verifier-gate")
    monkeypatch.setattr(gate, "is_quick_turn", lambda session_id: False)
    monkeypatch.setattr(gate, "_git_root", lambda cwd: str(tmp_path))
    monkeypatch.setattr(gate, "_diff", lambda root, files=None: (["x = 1"], ["a.py"]))
    monkeypatch.setattr(gate, "_tests_failing", lambda root: False)
    monkeypatch.setattr(gate, "check_file_verified", lambda s, p: (False, "no stamp"))

    def _run(session_id):
        payload = json.dumps({"session_id": session_id, "cwd": str(tmp_path)})
        monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
        assert gate.main() == 0
        return capsys.readouterr().err

    return _run


def test_a_nit_round_is_not_silenced_by_nudges_from_earlier_rounds(gate, run_stop):
    """A NITS: stamp is progress, so it clears the cap the way a good-cop stamp
    does. Without that, a session that spent most of its budget on earlier
    rounds gets one nit nudge and then permanent silence, leaving the file
    unverified with no actionable instruction left."""
    session = "nits-cap"
    _set_block_count(gate, session, gate.MAX_BLOCKS_PER_SESSION - 1)
    _write_stamps(gate, session, [{"agent": "bad-cop", "covers": [], "nits_only": True}])

    first = run_stop(session)
    assert "NITS:" in first
    assert first.count("[verifier-gate]") == 1

    second = run_stop(session)
    assert "NITS:" in second, "the nit instruction stopped reaching the model"
    assert "Staying quiet" not in second


def test_the_cap_still_silences_a_round_that_made_no_progress(gate, run_stop):
    """The other half: a stage with no new evidence must still run out of
    nudges, or the cap stops guarding against a stuck loop."""
    session = "handoff-cap"
    _set_block_count(gate, session, gate.MAX_BLOCKS_PER_SESSION - 1)
    _write_stamps(gate, session, [{"agent": "bad-cop", "covers": [], "nits_only": False}])

    assert "Spawn good-cop NOW" in run_stop(session)
    assert "Staying quiet" in run_stop(session)


def test_a_nit_round_leaves_the_counter_where_a_stamped_fix_does(gate, run_stop):
    """Both progress stages reset then bump, so one round of either lands on 1
    rather than accumulating across rounds."""
    for session, stamp in (
        ("nits-count", {"agent": "bad-cop", "covers": [], "nits_only": True}),
        ("fix-count", {"agent": "good-cop", "covers": ["a.py"]}),
    ):
        _set_block_count(gate, session, gate.MAX_BLOCKS_PER_SESSION - 1)
        _write_stamps(gate, session, [stamp])
        run_stop(session)
        assert _read_block_count(gate, session) == 1
