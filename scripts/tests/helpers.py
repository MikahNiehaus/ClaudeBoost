"""
Shared helpers for ClaudeBoost hook tests.

Import from here — not from conftest — since pytest's conftest.py
is not a reliable importable module across different rootdir configurations.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# scripts/ is one level up from scripts/tests/
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
COVERAGERC = Path(__file__).resolve().parent.parent.parent / ".coveragerc"

# Names a subprocess needs from the OS to start and behave like a normal
# process. Everything else is dropped, so a hook's behaviour comes from the
# fixture and from env_overrides — never from whatever the developer's shell
# happens to export. This is an allowlist for the same reason tox's passenv is
# one (tox passes only PATH, plus SYSTEMROOT and PATHEXT on Windows):
# a denylist of "known dangerous" names goes stale the moment someone adds a
# toggle, and it fails silently on exactly one machine. This repo's hooks read
# CLAUDEBOOST_*, CLEAN_RAG_*, RAG_*, CLAUDE_* and DISABLE_TELEMETRY; a real
# `CLAUDEBOOST_BASH_GUARD=off` and a real `DISABLE_TELEMETRY=1` in the ambient
# environment turned 106 of these tests into no-ops that still passed the
# exit-code assertions.
_ENV_ALLOWLIST = frozenset({
    # process/OS basics
    "PATH", "PATHEXT", "COMSPEC", "OS", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    # home and temp — Path.home() and tempfile need these
    "HOME", "HOMEDRIVE", "HOMEPATH", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR",
    # interpreter — PYTHONPATH carries conftest's sitecustomize for coverage
    "PYTHONPATH", "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8",
    "LANG", "LC_ALL",
})


def hook_env(env_overrides: dict | None = None) -> dict:
    """Build a hermetic environment for a hook subprocess.

    Only _ENV_ALLOWLIST names are inherited; env_overrides is applied last, so
    a test that wants an ambient toggle (CLAUDEBOOST_BASH_GUARD=off,
    DISABLE_TELEMETRY=1) must ask for it by name and gets it.

    Every subprocess spawn under scripts/tests/ routes through here, including
    the ad-hoc ones that pass their own env= to subprocess.run.
    test_helpers_env.test_no_test_builds_a_subprocess_env_from_os_environ
    enforces that by scanning the source, so the sentence above stays true
    without depending on anyone remembering it.
    """
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
    env.update(env_overrides or {})
    return env


def isolate_path_to(monkeypatch, *dirs: Path) -> None:
    """Point PATH at `dirs` only, plus the minimum the OS needs to spawn.

    For in-process tests, which do not go through hook_env but need the same
    guarantee: a test that PREPENDS a shim to the real PATH is not isolated.
    If the tool it shims is also installed for real, lookup order decides which
    one answers, and the test passes or fails on what the machine happens to
    have rather than on the code.

    Windows keeps SystemRoot and System32 when the OS names them, so a shim
    that shells out to a normal system tool still works. They are read from the
    environment rather than written as a literal: the Windows directory is not
    always on C:, and a path this file invents is a portability bug waiting for
    a different machine.
    """
    entries = [str(d) for d in dirs]
    system_root = os.environ.get("SystemRoot") if os.name == "nt" else None
    if system_root:
        entries += [system_root, str(Path(system_root) / "System32")]
    monkeypatch.setenv("PATH", os.pathsep.join(entries))


def run_hook(
    script_name: str,
    fixture: dict,
    env_overrides: dict | None = None,
    base_dir: Path | None = None,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess:
    """Run a hook script with a JSON fixture on stdin, return the result.

    base_dir overrides SCRIPTS_DIR for hooks that live elsewhere (e.g.
    clean-rag/hooks/) — defaults to SCRIPTS_DIR for every other hook.

    cwd sets the subprocess working directory. Pass a temp dir for any hook that
    shells out to git: without it the hook inherits pytest's cwd, which is this
    repo, and reads whatever happens to be uncommitted right now. tdd-guard.py
    did exactly that, so its strict-mode test passed on a clean tree and failed
    on a dirty one. A test whose result depends on your working tree is not
    testing the hook.

    The environment is scrubbed the same way and for the same reason — see
    hook_env. Name anything the hook should see in env_overrides.
    """
    script = (base_dir or SCRIPTS_DIR) / script_name
    env = hook_env(env_overrides)
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(fixture).encode(),
        capture_output=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def run_script(
    script_name: str,
    args: list | None = None,
    env_overrides: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a CLI script with optional args (no stdin fixture), return the result."""
    script = SCRIPTS_DIR / script_name
    env = hook_env(env_overrides)
    return subprocess.run(
        [sys.executable, str(script)] + (args or []),
        capture_output=True,
        env=env,
        input=b"",
    )


def pretooluse(tool_name: str, tool_input: dict) -> dict:
    """Minimal PreToolUse stdin fixture."""
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.json",
        "cwd": "/test/cwd",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "effort": {"level": "medium"},
    }


def posttooluse(tool_name: str, tool_input: dict, tool_response: str = "") -> dict:
    """Minimal PostToolUse stdin fixture."""
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.json",
        "cwd": "/test/cwd",
        "permission_mode": "default",
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
        "effort": {"level": "medium"},
    }
