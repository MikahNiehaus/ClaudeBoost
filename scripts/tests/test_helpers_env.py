"""Tests for the hermetic subprocess environment in helpers.py.

Without these, reverting hook_env() to `{**os.environ, ...}` stays green on
any machine that does not happen to export the toggles — which is exactly how
`CLAUDEBOOST_BASH_GUARD=off` and `DISABLE_TELEMETRY=1` silently turned 106
hook tests into no-ops that still passed their exit-code assertions.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from helpers import hook_env, pretooluse, run_hook

TESTS_DIR = Path(__file__).resolve().parent


def _blocked_command() -> dict:
    """A command bash-guard.py blocks (exit 2) whenever the guard is on."""
    return pretooluse("Bash", {"command": "cd /repo && git status"})


def test_ambient_toggle_does_not_reach_the_hook(monkeypatch):
    """An off switch exported by the developer's shell must not disable the guard."""
    monkeypatch.setenv("CLAUDEBOOST_BASH_GUARD", "off")
    result = run_hook("bash-guard.py", _blocked_command())
    assert result.returncode == 2


def test_explicit_override_does_reach_the_hook(monkeypatch):
    """Opting in by name still works — scrubbing is not a ban."""
    monkeypatch.delenv("CLAUDEBOOST_BASH_GUARD", raising=False)
    result = run_hook(
        "bash-guard.py",
        _blocked_command(),
        env_overrides={"CLAUDEBOOST_BASH_GUARD": "off"},
    )
    assert result.returncode == 0


def test_scrubbing_is_not_limited_to_one_name(monkeypatch):
    """The mechanism is an allowlist, so any new toggle is dropped too."""
    monkeypatch.setenv("DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("SOME_FUTURE_CLAUDEBOOST_TOGGLE", "on")
    env = hook_env()
    assert "DISABLE_TELEMETRY" not in env
    assert "SOME_FUTURE_CLAUDEBOOST_TOGGLE" not in env


def test_os_essentials_survive():
    """PATH and the Windows basics are still inherited, or nothing would run."""
    env = hook_env()
    assert env.get("PATH")
    import os
    for name in ("SYSTEMROOT", "TEMP"):
        if name in os.environ:
            assert name in env


# ---------------------------------------------------------------------------
# Drift guard
#
# The mechanism above only holds for spawns that actually call hook_env. Nine
# raw `{**os.environ}` spawns sat alongside it for a while and nobody noticed,
# because a raw spawn looks identical to a routed one at the call site. So scan
# the source instead of trusting review, the same way
# clean-rag/tests/test_skill_rag_routes.py scans command files for a stale
# `scope=` parameter and fails with a file:line list.
# ---------------------------------------------------------------------------

#: The three ways this repo has actually built an env from the ambient one.
_RAW_ENV = re.compile(r"\*\*\s*os\.environ|dict\(\s*os\.environ\s*\)|os\.environ\.copy\(\)")


def raw_env_spawns(directory: Path) -> list[tuple[str, int, str]]:
    """Every line under *directory* that builds a subprocess env from os.environ."""
    hits = []
    for path in sorted(directory.glob("*.py")):
        if path.name == Path(__file__).name:
            continue  # this file quotes the patterns it looks for
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _RAW_ENV.search(line):
                hits.append((path.name, lineno, line.strip()))
    return hits


def test_no_test_builds_a_subprocess_env_from_os_environ():
    """Every spawn goes through hook_env, so no new one can inherit silently."""
    raw = raw_env_spawns(TESTS_DIR)
    assert raw == [], (
        "These build a subprocess environment from the ambient one. Use "
        "hook_env(overrides) from helpers instead - see its docstring:\n"
        + "\n".join(f"  {name}:{lineno}  {line}" for name, lineno, line in raw)
    )


@pytest.mark.parametrize("spawn", [
    'env = {**os.environ}',
    'env={**os.environ, "CLAUDEBOOST_HOME": str(home)}',
    'env = dict(os.environ)',
    'env = os.environ.copy()',
])
def test_the_scan_catches_a_reintroduced_raw_spawn(tmp_path, spawn):
    """Proves the test above is not vacuous — it fails on each real form."""
    (tmp_path / "test_scratch.py").write_text(
        f"import os, subprocess\ndef test_x():\n    {spawn}\n", encoding="utf-8"
    )
    assert raw_env_spawns(tmp_path) == [("test_scratch.py", 3, spawn)]
