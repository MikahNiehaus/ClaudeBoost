"""claim_session_once decides whether a hook says its full text or a pointer.

Nothing covered it, which is why two payload shapes reached it unhandled. Both
end in the same place, the block being emitted in full on every single message,
which is the 164,012 token cost this guard was added to remove.

The shapes: a session id that is present with the wrong type, which raised
AttributeError on .encode(), and a state directory that exists as a file, where
mkdir(parents=True, exist_ok=True) raises FileExistsError rather than passing.
The pathlib docs are explicit about the second: exist_ok suppresses the error
only when the last path component is already a directory
(https://docs.python.org/3/library/pathlib.html#pathlib.Path.mkdir).
"""
import importlib.util
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]


@pytest.fixture()
def state(tmp_path, monkeypatch):
    """A fresh research_state bound to its own CLEAN_RAG_HOME."""
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    path = str(CLEAN_RAG / "hooks" / "research_state.py")
    spec = importlib.util.spec_from_file_location("research_state_once_guard", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    yield mod, tmp_path
    sys.modules.pop(spec.name, None)


def test_first_claim_emits_and_the_second_does_not(state):
    mod, _ = state
    assert mod.claim_session_once("sess-a", "rag-contract", "fp1") is True
    assert mod.claim_session_once("sess-a", "rag-contract", "fp1") is False


def test_a_changed_fingerprint_emits_again(state):
    mod, _ = state
    mod.claim_session_once("sess-a", "rag-contract", "fp1")
    assert mod.claim_session_once("sess-a", "rag-contract", "fp2") is True


def test_two_sessions_do_not_share_a_flag(state):
    mod, _ = state
    mod.claim_session_once("sess-a", "rag-contract", "fp1")
    assert mod.claim_session_once("sess-b", "rag-contract", "fp1") is True


@pytest.mark.parametrize("session_id", [12345, None, ["sess"], {"id": "sess"}, b"sess"])
def test_a_mistyped_session_id_still_claims_once(state, session_id):
    """Not a crash, and not a block re sent forever: claimed, then quiet.

    code-pattern-inject.py and verify-after-edit.py read session_id with a bare
    .get, so whatever the payload holds arrives here as is.
    """
    mod, _ = state
    assert mod.claim_session_once(session_id, "reuse-check") is True
    assert mod.claim_session_once(session_id, "reuse-check") is False


def test_a_lone_surrogate_in_the_session_id_does_not_raise(state):
    mod, _ = state
    assert mod.claim_session_once("sess-\ud800", "reuse-check") is True
    assert mod.claim_session_once("sess-\ud800", "reuse-check") is False


def test_it_fails_open_when_the_state_directory_is_a_file(state):
    """True every time, so the rule gets said even with nowhere to record it."""
    mod, home = state
    (home / "state").mkdir()
    (home / "state" / "research").write_text("not a directory", encoding="utf-8")

    assert mod.claim_session_once("sess-a", "rag-contract", "fp1") is True
    assert mod.claim_session_once("sess-a", "rag-contract", "fp1") is True
