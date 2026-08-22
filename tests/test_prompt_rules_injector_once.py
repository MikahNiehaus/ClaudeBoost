"""
prompt-rules-injector.py states the search contract once per session, not once
per prompt, driven through the real script end to end.

It was emitting about 521 tokens on every message. Roughly half of that was a
[Rules] paragraph (plain writing, no dashes, confirm before irreversible
actions, keep context.md current) that is identical on every turn and now lives
in CLAUDE.md, read once into the cached prefix. The half that remains is the
clean-rag search contract, which is worth saying, but only when it is new or
has actually changed.

Note this hook writes plain text to stdout rather than JSON. On
UserPromptSubmit that is injected as context verbatim, so an empty stdout is
what "say nothing" looks like.

Run: python -m pytest tests/test_prompt_rules_injector_once.py -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INJECTOR = REPO / "scripts" / "prompt-rules-injector.py"


@pytest.fixture
def home(tmp_path):
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "workspaces.json").write_text(json.dumps({}))
    (tmp_path / "clean-rag").mkdir()
    return tmp_path


@pytest.fixture
def temp(tmp_path):
    d = tmp_path / "hooktmp"
    d.mkdir()
    return d


def run_injector(home, temp, prompt, session_id="s1", cwd=None):
    env = dict(os.environ)
    env["CLAUDEBOOST_HOME"] = str(home)
    env["TMPDIR"] = str(temp)
    env["TEMP"] = str(temp)
    payload = json.dumps({
        "prompt": prompt,
        "session_id": session_id,
        "cwd": str(cwd or home),
        "hook_event_name": "UserPromptSubmit",
    })
    proc = subprocess.run(
        [sys.executable, str(INJECTOR)],
        input=payload, capture_output=True, text=True,
        env=env, cwd=str(cwd or home), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


P1 = "please refactor the search module and add tests for it"
P2 = "now update the docs to match that change"
P3 = "and run the full test suite for me"


def test_contract_is_stated_once_then_the_hook_goes_quiet(home, temp):
    first = run_injector(home, temp, P1)
    assert "/search" in first, "the first prompt of a session should get the contract"

    assert run_injector(home, temp, P2) == ""
    assert run_injector(home, temp, P3) == ""


def test_rules_paragraph_is_gone(home, temp):
    """That text is in CLAUDE.md now. Repeating it here is what it cost to fix."""
    first = run_injector(home, temp, P1)
    for gone in ("[Rules]", "throat clearing", "filler intensifiers",
                 "flag safety concerns once"):
        assert gone not in first, f"{gone!r} is still being injected per prompt"


def test_each_session_is_told_once(home, temp):
    assert "/search" in run_injector(home, temp, P1, session_id="alpha")
    assert run_injector(home, temp, P2, session_id="alpha") == ""
    assert "/search" in run_injector(home, temp, P3, session_id="beta")


def test_it_speaks_again_when_the_contract_changes(home, temp, tmp_path):
    """
    Quiet is conditional on nothing having changed, not on having spoken once.

    A different project means a different `sources` line, and the model needs
    the new one.
    """
    assert "/search" in run_injector(home, temp, P1)
    assert run_injector(home, temp, P2) == ""

    other = tmp_path / "other-project"
    other.mkdir()
    again = run_injector(home, temp, P3, cwd=other)
    assert "/search" in again
    assert str(other).replace("\\", "/") in again


def test_no_dead_endpoints_are_advertised(home, temp):
    """8612 and /context were deleted with mcp-rag-server."""
    first = run_injector(home, temp, P1)
    assert "8612" not in first
    assert "/context" not in first
    assert '"scope"' not in first, "the live server takes sources, not scope"
