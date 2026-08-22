"""
rag-enforce.py announces a clean-rag outage once per outage, not once per prompt.

The warning text is byte identical every time it fires. Injected context is
re-read by every later request in the session, so repeating it while the server
stays down costs about 116 tokens a turn to say nothing new, and session-primer
already reports the same transition once.

What must keep working: the first prompt of an outage still says it, a fresh
conversation is still told, and a healthy turn rearms the warning so the next
outage is announced again.

These drive the real hook as a subprocess with the stdin payload Claude Code
sends, with CLEAN_RAG_PORT pointed at a closed port so the outage is genuine.

Run: python -m pytest tests/test_rag_enforce_offline_once.py -v
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "clean-rag" / "hooks" / "rag-enforce.py"
MARKER_GLOB = "offline-reported-*"


def _server_reachable() -> bool:
    """Is the real clean-rag actually answering? Its port comes from its config."""
    import urllib.request
    sys.path.insert(0, str(REPO / "scripts"))
    try:
        from rag_port import rag_url
        with urllib.request.urlopen(rag_url("/status"), timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def isolated_home(tmp_path):
    """
    A throwaway CLEAN_RAG_HOME with the automatic restart switched off.

    Any test that forces CLEAN_RAG_PORT must use this. rag-enforce reacts to an
    unreachable server by running server_ctl start, which inherits the forced
    port, so without the marker a test restarts the real server somewhere
    random. The marker is the same one `server_ctl stop` writes.
    """
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "server-stopped-by-user").write_text("test", encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def clean_markers():
    """These live in the real clean-rag state dir, so clear them either side."""
    state = REPO / "clean-rag" / "state"

    def wipe():
        for pattern in (MARKER_GLOB, "last-project-context-*"):
            for p in state.glob(pattern):
                try:
                    p.unlink()
                except OSError:
                    pass

    wipe()
    yield
    wipe()


def run_hook(prompt, session_id, port, isolated_home=None):
    """
    port=None means do not override CLEAN_RAG_PORT, so the real server is used.

    When a port IS forced, CLEAN_RAG_HOME must point somewhere disposable and
    carry the stop marker. Forcing a closed port makes rag-enforce believe the
    server is down, and its self-heal then runs server_ctl start, which inherits
    CLEAN_RAG_PORT from this environment. That is not hypothetical: an earlier
    version of this file restarted the developer's live server on a random
    ephemeral port (57933) and left it there. The marker suppresses self-heal,
    and the tmp home keeps the cooldown stamp out of the real state directory.
    """
    env = dict(os.environ)
    if port is not None:
        assert isolated_home is not None, "a forced port requires an isolated home"
        env["CLEAN_RAG_HOME"] = str(isolated_home)
        env["CLEAN_RAG_PORT"] = str(port)
    else:
        # Pinned, not inherited. tests/test_rag_enforce_slash_commands.py points
        # CLEAN_RAG_HOME at a tmp dir, and depending on ambient env made this
        # file pass alone and skip inside the full suite, which is the worst of
        # both: a test that reports success while protecting nothing.
        env["CLEAN_RAG_HOME"] = str(REPO / "clean-rag")
    payload = json.dumps({
        "prompt": prompt,
        "session_id": session_id,
        "cwd": str(REPO),
        "hook_event_name": "UserPromptSubmit",
    })
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload, capture_output=True, text=True,
        env=env, cwd=str(REPO), timeout=180,
    )
    return proc.stdout


P1 = "please refactor the search module and add tests for it"
P2 = "now update the docs to match that change"
P3 = "and run the full test suite for me"


def test_outage_is_announced_once_then_the_hook_goes_quiet(isolated_home):
    dead = _closed_port()
    first = run_hook(P1, "alpha", dead, isolated_home)
    assert "did not answer on port" in first

    assert run_hook(P2, "alpha", dead, isolated_home).strip() == ""
    assert run_hook(P3, "alpha", dead, isolated_home).strip() == ""


def test_a_fresh_conversation_is_still_told(isolated_home):
    """The marker is per session. A new conversation has not heard it yet."""
    dead = _closed_port()
    assert "did not answer on port" in run_hook(P1, "alpha", dead, isolated_home)
    assert run_hook(P2, "alpha", dead, isolated_home).strip() == ""
    assert "did not answer on port" in run_hook(P3, "beta", dead, isolated_home)


def test_the_warning_still_names_how_to_start_it(isolated_home):
    """Quieting the repeat must not cost the actionable part of the message."""
    out = run_hook(P1, "alpha", _closed_port(), isolated_home)
    assert "server_ctl.py start" in out
    assert "no injected research context" in out


def test_project_context_is_stated_once_per_state():
    """
    The Project Context block is one of a few fixed strings, and whichever
    applies is identical every turn until the index state actually moves. While
    the server is down it can never move, so repeating it costs about 39 tokens
    a prompt forever.

    Runs against the real configured port, because forcing an unknown one skips
    this path. Whether it reports indexed or not indexed does not matter here;
    what matters is that it is not restated when nothing changed.
    """
    if not _server_reachable():
        pytest.skip("clean-rag is not running; the project context block only "
                    "exists when /status answers, so there is nothing to assert")

    first = run_hook(P1, "alpha", None)
    assert "## Project Context" in first, (
        "the server answered, so the first prompt of a session must state the "
        "project context"
    )

    second = run_hook(P2, "alpha", None)
    assert "## Project Context" not in second, \
        "project context repeated while the index state had not changed"


def test_steady_state_emits_nothing_at_all(isolated_home):
    """
    Once a session has been told both things, a prompt that changes nothing
    should cost zero. This is the whole point of the change.
    """
    dead = _closed_port()
    run_hook(P1, "alpha", dead, isolated_home)
    assert run_hook(P2, "alpha", dead, isolated_home).strip() == ""
    assert run_hook(P3, "alpha", dead, isolated_home).strip() == ""
