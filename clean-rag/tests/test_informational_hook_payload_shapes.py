"""The informational hooks must exit 0 on input they cannot read.

These five never gate anything. Each says so in its own docstring:
verify-after-edit.py ("never blocks. Exit 0 always"), reindex-after-edit.py
("0 = always (PostToolUse hooks should not block)"), graph-context-inject.py
("Exit code is always 0"), and research-record.py / verifier-record.py ("Never
blocks. Its only job is to write down what happened"). This pins the code to
those docstrings.

Exit 1 is the failure being tested for, and it is not a harmless synonym for 0.
It means an exception escaped, so Claude Code shows the user a raw traceback
carrying absolute local paths, and on the two recording hooks the stamp that
was supposed to be written silently is not. Every payload below is valid JSON
of an unexpected shape, which is exactly what a naive payload.get(...) chain
raises on: json.loads accepts null, a bare string, a number and a list just as
happily as an object.

Sibling of test_agent_bash_guard_payload_shapes.py, which asserts the opposite
verdict (2, fail closed) for the guards that do gate. The two contracts are
deliberately different, so they are pinned separately.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"

HOOKS_UNDER_TEST = [
    "graph-context-inject.py",
    "reindex-after-edit.py",
    "research-record.py",
    "verifier-record.py",
    "verify-after-edit.py",
]

# Valid JSON, unexpected shape. Every one of these breaks a naive .get chain.
MALSHAPED_PAYLOADS = [
    "null",
    "true",
    "123",
    '"hello"',
    "[]",
    "[1,2,3]",
    '{"tool_name": null}',
    '{"tool_name": 123}',
    '{"tool_name": ["Edit"]}',
    '{"tool_name": "Edit", "tool_input": null}',
    '{"tool_name": "Edit", "tool_input": "x"}',
    '{"tool_name": "Edit", "tool_input": []}',
    '{"tool_name": "Edit", "tool_input": {"file_path": null}}',
    '{"tool_name": "Edit", "tool_input": {"file_path": 123}}',
    '{"tool_name": "Task", "tool_response": null, "tool_input": {"subagent_type": "swiper"}}',
    '{"tool_name": "Task", "tool_response": 5, "tool_input": {"subagent_type": "swiper"}}',
    '{"tool_name": "Task", "tool_input": null, "tool_response": "COVERS: a.py"}',
]

UNPARSEABLE_PAYLOADS = ["{not valid json", "", "   \n  "]


# What a Python process needs from the OS to start at all, plus CLEAN_RAG_HOME
# and the temp variables, pointed at a scratch tree so nothing here can reach
# the real state directory. Nothing is inherited: a hook that only behaves
# because of what happened to be in this machine's environment is an undeclared
# dependency, not a passing test.
_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env(scratch: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}
    env["TEMP"] = env["TMP"] = env["TMPDIR"] = str(scratch)
    env["CLEAN_RAG_HOME"] = str(scratch / "clean-rag")
    return env


def _run(hook: str, stdin_text: str, scratch: Path) -> subprocess.CompletedProcess:
    # encoding and errors named explicitly. text=True alone decodes with
    # locale.getpreferredencoding(), cp1252 on this machine, and a hook that
    # prints a path with a non cp1252 character then kills the reader thread:
    # subprocess.run still returns, .stderr comes back None, and the assertion
    # below fails with AttributeError instead of showing what the hook said.
    return subprocess.run(
        [sys.executable, str(HOOKS / hook)],
        input=stdin_text,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=_hermetic_env(scratch),
        timeout=120,
    )


@pytest.mark.parametrize("hook", HOOKS_UNDER_TEST)
@pytest.mark.parametrize("payload", MALSHAPED_PAYLOADS)
def test_malshaped_payload_exits_zero_without_a_traceback(hook, payload, tmp_path):
    result = _run(hook, payload, tmp_path)
    assert "Traceback" not in result.stderr, (
        f"{hook} crashed on {payload!r} instead of ignoring it:\n{result.stderr}"
    )
    assert result.returncode == 0, (
        f"{hook} returned {result.returncode} for {payload!r}. Its docstring "
        "promises 0 on every payload; 1 means an exception escaped main()."
    )


@pytest.mark.parametrize("hook", HOOKS_UNDER_TEST)
@pytest.mark.parametrize("payload", UNPARSEABLE_PAYLOADS)
def test_unparseable_payload_exits_zero(hook, payload, tmp_path):
    result = _run(hook, payload, tmp_path)
    assert result.returncode == 0, (
        f"{hook} returned {result.returncode} for stdin {payload!r}."
    )


@pytest.mark.parametrize("hook", HOOKS_UNDER_TEST)
def test_a_well_formed_payload_still_exits_zero(hook, tmp_path):
    """The shape guards must not have turned into a refusal for real input.

    A hook that returns 0 for everything passes the tests above whether or not
    it still does its job, so this pins the ordinary case too.
    """
    payload = json.dumps({
        "session_id": "s1",
        "tool_name": "Edit",
        "tool_input": {"file_path": str(tmp_path / "example.py")},
    })
    result = _run(hook, payload, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
