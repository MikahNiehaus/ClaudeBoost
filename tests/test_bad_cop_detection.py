"""verifier-gate.py routes its nudge from which cop stamped last.

Was written against `_bad_cop_ran_with_bugs()`, which no longer exists. That
function scanned every stamp and answered "did bad-cop ever report bugs". It was
replaced by `loop_stage()` over `_last_verifier_agent()`, which reads only the
MOST RECENT stamp. The change is deliberate and documented in
`_last_verifier_agent`: scanning any stamp meant an empty-covers bad-cop stamp
from round one kept redirecting to good-cop long after good-cop had stamped and
the loop had moved on.

Rewritten against the current API, keeping every property the old file asserted
and adding the last-stamp-wins rule the old one could not express. One property
the old file recorded as a live BUG (stamps as a non-list raised TypeError
instead of failing open) is now genuinely fixed, so it is asserted as passing
rather than as a known defect.

Three stages, and the whole point is that they are distinguishable:
  bad-cop stamped with EMPTY covers  -> it found bugs   -> good-cop is next
  good-cop stamped with covers       -> fix is stamped  -> bad-cop re-checks
  anything else                      -> no verifier yet -> bad-cop is next
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
sys.path.insert(0, str(HOOKS_DIR))


def _write_record(home: Path, session_id: str, stamps) -> Path:
    """Write a session record where _record_path() will look for it."""
    state = home / "state" / "verifier"
    state.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    path = state / f"session-{key}.json"
    path.write_text(json.dumps({"session_id": session_id, "stamps": stamps}),
                    encoding="utf-8")
    return path


def _write_raw(home: Path, session_id: str, text: str) -> Path:
    """Write arbitrary bytes to the record path, for the malformed-input cases."""
    state = home / "state" / "verifier"
    state.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256((session_id or "no-session").encode("utf-8")).hexdigest()[:16]
    path = state / f"session-{key}.json"
    path.write_text(text, encoding="utf-8")
    return path


SESSION = "test-session-adversarial"


@pytest.fixture()
def vg(tmp_path, monkeypatch):
    """verifier-gate loaded with CLEAN_RAG_HOME pointed at a temp dir.

    _state_dir() resolves CLEAN_RAG_HOME at call time through _clean_rag_home(),
    so verifier_state has to be reloaded after the env var is set, and
    verifier-gate.py loaded fresh so it closes over the reloaded _record_path.
    """
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    import verifier_state
    importlib.reload(verifier_state)

    spec = importlib.util.spec_from_file_location(
        "verifier_gate_under_test", HOOKS_DIR / "verifier-gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._test_home = tmp_path
    return mod


class TestBadCopFoundBugs:
    """bad-cop stamps EMPTY covers when it found something. That is the signal
    good-cop is next, so every spelling of empty has to read the same."""

    @pytest.mark.parametrize("stamp,label", [
        ({"agent": "bad-cop", "at": 1.0, "covers": []}, "covers=[]"),
        ({"agent": "bad-cop", "at": 1.0}, "covers key missing"),
        ({"agent": "bad-cop", "at": 1.0, "covers": None}, "covers=None"),
    ])
    def test_empty_covers_means_bugs_found(self, vg, stamp, label):
        _write_record(vg._test_home, SESSION, [stamp])
        assert vg.loop_stage(SESSION) == vg.STAGE_BUGS_FOUND, label

    def test_bad_cop_with_real_covers_is_a_clean_pass(self, vg):
        """Non-empty covers is bad-cop finding nothing, which ends the loop.
        Reading it as 'bugs found' would send good-cop after a clean pass."""
        _write_record(vg._test_home, SESSION, [
            {"agent": "bad-cop", "at": 1.0, "covers": ["some/file.py"]},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER


class TestGoodCopStampedFix:
    def test_good_cop_with_covers_is_a_stamped_fix(self, vg):
        _write_record(vg._test_home, SESSION, [
            {"agent": "good-cop", "at": 1.0, "covers": ["some/file.py"]},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_FIX_STAMPED

    def test_good_cop_with_empty_covers_is_not_a_stamped_fix(self, vg):
        """good-cop's job is to stamp what it fixed. Empty covers is not a fix,
        and must not read as one just because good-cop was the last to run."""
        _write_record(vg._test_home, SESSION, [
            {"agent": "good-cop", "at": 1.0, "covers": []},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER


class TestOnlyTheLastStampCounts:
    """The reason _bad_cop_ran_with_bugs was replaced. Scanning every stamp meant
    round one's finding kept firing after the loop had already moved past it."""

    def test_a_later_clean_pass_overrides_an_earlier_finding(self, vg):
        _write_record(vg._test_home, SESSION, [
            {"agent": "bad-cop", "at": 1.0, "covers": []},
            {"agent": "good-cop", "at": 2.0, "covers": ["fixed.py"]},
            {"agent": "bad-cop", "at": 3.0, "covers": ["fixed.py"]},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    def test_a_later_finding_overrides_an_earlier_clean_pass(self, vg):
        _write_record(vg._test_home, SESSION, [
            {"agent": "bad-cop", "at": 1.0, "covers": ["clean.py"]},
            {"agent": "bad-cop", "at": 2.0, "covers": []},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_BUGS_FOUND

    def test_mid_loop_good_cop_stamp_routes_to_the_recheck(self, vg):
        _write_record(vg._test_home, SESSION, [
            {"agent": "bad-cop", "at": 1.0, "covers": []},
            {"agent": "good-cop", "at": 2.0, "covers": ["fixed.py"]},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_FIX_STAMPED


class TestFailsOpen:
    """A gate that raises on bad input blocks the turn for a reason that has
    nothing to do with the code under review. Every one of these returns the
    neutral stage rather than throwing."""

    def test_no_record_file(self, vg):
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    def test_malformed_json(self, vg):
        _write_raw(vg._test_home, SESSION, "{not valid json ][")
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    def test_stamps_key_missing(self, vg):
        _write_raw(vg._test_home, SESSION, json.dumps({"session_id": SESSION}))
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    def test_empty_stamps_list(self, vg):
        _write_record(vg._test_home, SESSION, [])
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    @pytest.mark.parametrize("stamps", [42, "bad-cop", {"agent": "bad-cop"}, None])
    def test_stamps_is_not_a_list(self, vg, stamps):
        """The old implementation raised TypeError here: `any(... for s in 42)`.
        Its contract said fail open, and only the caller's outer except block
        kept the gate from dying. _last_verifier_agent's isinstance check fixes
        it at the source, so assert the fix rather than the defect."""
        _write_raw(vg._test_home, SESSION,
                   json.dumps({"session_id": SESSION, "stamps": stamps}))
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    def test_agent_key_missing(self, vg):
        _write_record(vg._test_home, SESSION, [{"at": 1.0, "covers": []}])
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER

    def test_an_unknown_agent_is_not_a_cop(self, vg):
        _write_record(vg._test_home, SESSION, [
            {"agent": "quick-cop", "at": 1.0, "covers": []},
        ])
        assert vg.loop_stage(SESSION) == vg.STAGE_NO_VERIFIER, (
            "quick-cop stamps nothing and must never satisfy this gate"
        )


class TestTheThreeStagesAreDistinct:
    def test_stage_constants_do_not_collide(self, vg):
        """Routing branches on these by value. Two equal constants would make
        two different situations produce the same nudge, silently."""
        stages = {vg.STAGE_NO_VERIFIER, vg.STAGE_BUGS_FOUND, vg.STAGE_FIX_STAMPED}
        assert len(stages) == 3

    def test_record_path_is_stable_for_a_session(self, vg):
        from verifier_state import _record_path
        assert _record_path(SESSION) == _record_path(SESSION)
        assert _record_path(SESSION) != _record_path(SESSION + "-other")
