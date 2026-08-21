"""verifier-gate.py's stage messages, driven through the real main() end to end
(a temp git repo with an uncommitted code change, a seeded verifier stamp, the
hook's actual stdin payload), not just loop_stage() in isolation.

The BLOCKED -> NUDGE rewording dropped the trailing space that used to sit
before the next literal was concatenated on, in two of the three stage
branches. That turns "found real bugs, these files" into a merged run of
words with no separating space, and worse, "stamped VERIFIED: but" into
"VERIFIED: butthese files" with the word and the next sentence fused together.

Run: python -m pytest tests/test_verifier_gate_nudge_text.py -v
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "clean-rag" / "hooks"
VERIFIER_GATE_PY = HOOKS_DIR / "verifier-gate.py"

SESSION = "nudge-text-check-session"


def _load_hook(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, HOOKS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def temp_repo_with_uncommitted_change(tmp_path):
    """A throwaway git repo with two committed files, both then edited
    uncommitted, so verifier-gate.py's own git diff detection finds two real
    code changes. Two files matter: seeding a stamp that covers only one of
    them leaves the other unverified, which is what actually makes main()
    reach the print branch instead of exiting early because everything is
    already verified."""
    repo = tmp_path / "repo"
    repo.mkdir()
    widget = repo / "widget.py"
    gadget = repo / "gadget.py"
    widget.write_text("def widget():\n    return 1\n", encoding="utf-8")
    gadget.write_text("def gadget():\n    return 1\n", encoding="utf-8")

    def git(*args):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "test")
    git("add", "widget.py", "gadget.py")
    git("commit", "-q", "-m", "initial")

    widget.write_text("def widget():\n    return 2\n", encoding="utf-8")
    gadget.write_text("def gadget():\n    return 2\n", encoding="utf-8")
    return repo


@pytest.fixture
def verifier_state_module(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    monkeypatch.setenv("CLEAN_RAG_PORT", "9")  # unreachable: _tests_failing() -> False
    module = _load_hook("verifier_state.py", "verifier_state_for_nudge_text_test")
    return module


def _seed_stamp(verifier_state_module, agent: str, covers):
    report = (
        f"whatever\nVERIFIED: {' '.join(covers)}" if covers else "whatever\nHANDOFF: 1 finding"
    )
    verifier_state_module.record_verifier(session_id=SESSION, report=report, agent_type=agent)


def _run_verifier_gate(repo_path):
    """Relies on CLEAN_RAG_HOME and CLEAN_RAG_PORT already being set in the
    process environment by the verifier_state_module fixture's monkeypatch."""
    import os

    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, str(VERIFIER_GATE_PY)],
        input=json.dumps(
            {"session_id": SESSION, "cwd": str(repo_path), "stop_hook_active": False}
        ).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=60,
    )
    return proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def test_bad_cop_found_bugs_message_has_a_space_before_the_file_list(
    temp_repo_with_uncommitted_change, verifier_state_module
):
    _seed_stamp(verifier_state_module, "bad-cop", [])
    code, err = _run_verifier_gate(temp_repo_with_uncommitted_change)
    assert code == 0
    assert "found real bugs" in err  # sanity: we did reach the right branch
    # Whatever separator sits before the em dash (a plain ASCII space, unaffected
    # by this diff), the character directly in front of "these files" is the
    # part the BLOCKED -> NUDGE rewording touched: it used to be a trailing
    # space, now it is the em dash itself with nothing after it.
    these_idx = err.index("these files")
    char_before = err[these_idx - 1]
    assert char_before.isspace(), (
        f"no whitespace directly before 'these files', found {char_before!r} "
        f"instead — the BLOCKED -> NUDGE rewording dropped the trailing space "
        f"that used to separate the em dash from the next sentence.\nFull "
        f"message:\n{err}"
    )


def test_good_cop_stamped_message_has_a_space_before_the_file_list(
    temp_repo_with_uncommitted_change, verifier_state_module
):
    # Stamp only widget.py; gadget.py stays unverified so main() actually
    # reaches the print branch instead of exiting early with nothing to say.
    _seed_stamp(verifier_state_module, "good-cop", ["widget.py"])
    code, err = _run_verifier_gate(temp_repo_with_uncommitted_change)
    assert code == 0
    assert "stamped VERIFIED:" in err  # sanity: we did reach the right branch
    assert "butthese files" not in err, (
        f"'stamped VERIFIED: but' ran straight into 'these files' with no space "
        f"between them.\n{err}"
    )
