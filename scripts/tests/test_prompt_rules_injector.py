"""prompt-rules-injector.py's own session_id parsing and once-per-session guard.

Added by this diff: main() used to discard stdin entirely
(`sys.stdin.read() if not sys.stdin.isatty() else ""`, return value unused),
so there was no way to key `_emit_once` per session. It now parses the hook
payload and extracts session_id, falling back to "" on anything that is not
a JSON object.

Nothing exercised this before. clean-rag/tests/test_session_once_guard.py
covers the underlying research_state.claim_session_once primitive, but
nothing drove prompt-rules-injector.py's own main() end to end, so a broken
wire between "parse session_id" and "call _emit_once" would pass every
existing test while still emitting the block on every single message again,
which is the 164,012 token regression this mechanism exists to prevent.

Run as real subprocesses (not imported), because main() is written to run
that way (reads sys.stdin, prints to stdout) and reimporting it fights the
module-level `sys.path.insert` and `sys.stdout.reconfigure` side effects.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "scripts" / "prompt-rules-injector.py"


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A scratch CLAUDEBOOST_HOME with just enough of clean-rag to import."""
    shutil.copytree(REPO / "clean-rag" / "server", tmp_path / "clean-rag" / "server")
    (tmp_path / "clean-rag" / "hooks").mkdir(parents=True)
    shutil.copy(
        REPO / "clean-rag" / "hooks" / "research_state.py",
        tmp_path / "clean-rag" / "hooks" / "research_state.py",
    )
    (tmp_path / "clean-rag" / "state").mkdir(parents=True)
    (tmp_path / "state").mkdir(parents=True)
    return tmp_path


def _env(home: Path) -> dict:
    import os

    # Scrubbed: only what the hook and the interpreter actually need, so a
    # pass here is not secretly riding on this machine's ambient environment.
    keep = {}
    for var in ("SYSTEMROOT", "PATH", "TEMP", "TMP"):
        if os.environ.get(var):
            keep[var] = os.environ[var]
    keep["CLAUDEBOOST_HOME"] = str(home)
    keep["CLEAN_RAG_HOME"] = str(home / "clean-rag")
    return keep


def _run_hook(home: Path, payload) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(home),
        env=_env(home),
        timeout=20,
    )


def test_first_call_emits_second_call_same_session_is_silent(home):
    payload = {"session_id": "sess-real-uuid"}
    first = _run_hook(home, payload)
    second = _run_hook(home, payload)

    assert first.returncode == 0, first.stderr
    assert first.stdout.strip(), "first call must print the RAG block"
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "", (
        f"second call for the same session should be silent, got: {second.stdout!r}"
    )


def test_an_integer_session_id_still_suppresses_on_the_second_call(home):
    """A non-string session_id (a real payload shape, not just str) must not
    crash and must not re-emit forever."""
    payload = {"session_id": 4242}
    first = _run_hook(home, payload)
    second = _run_hook(home, payload)

    assert first.returncode == 0, first.stderr
    assert first.stdout.strip()
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == ""


def test_two_different_sessions_each_get_their_own_first_emit(home):
    a = _run_hook(home, {"session_id": "sess-a"})
    b = _run_hook(home, {"session_id": "sess-b"})

    assert a.stdout.strip(), "session a must emit"
    assert b.stdout.strip(), "session b must emit, independent of session a"


def test_malformed_json_on_stdin_does_not_crash_the_hook(home):
    result = _run_hook(home, "not valid json{{{")
    assert result.returncode == 0, result.stderr
    # No session_id resolvable, so it falls back to the empty session bucket,
    # but the hook must still run and still print something on a first call.
    assert result.stdout.strip(), result.stderr


def test_a_bare_json_list_on_stdin_does_not_crash(home):
    """json.loads accepts any JSON value; a list has no .get."""
    result = _run_hook(home, "[1, 2, 3]")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), result.stderr


def test_empty_stdin_does_not_crash(home):
    result = _run_hook(home, "")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), result.stderr
