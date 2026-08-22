"""
clean-rag's _wrap_command must not corrupt a compound shell command.

It routes hook commands through hook-run.py by splitting the interpreter off the
front and inserting the runner after it. That is right for
`"<python>" "<script>"` and wrong for anything with shell control flow.

scripts/setup.py writes a portable fallback chain for most hooks:

    if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then "$CLAUDEBOOST_PYTHON" script
    elif command -v python3 >/dev/null 2>&1; then python3 script
    ...

Splitting that on whitespace treats `if` as the interpreter and produces

    if "<runner>" command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then ...

which asks the shell to run hook-run.py with `command -v ...` as its arguments.
It fails, the `if` goes false, the elif branch runs the script unwrapped, and the
protection the wrapper exists to add is skipped, silently, on every hook written
in that form. 27 of them on a real machine after one install.

Run: python -m pytest tests/test_hook_wrapping_shell_safe.py -v
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNNER = str(Path.home() / ".claude" / "hook-run.py")

FALLBACK = (
    'if command -v "$CLAUDEBOOST_PYTHON" >/dev/null 2>&1; then '
    '"$CLAUDEBOOST_PYTHON" "$CLAUDEBOOST_HOME/scripts/compaction-save.py"; '
    'elif command -v python3 >/dev/null 2>&1; then '
    'python3 "$CLAUDEBOOST_HOME/scripts/compaction-save.py"; '
    'else py "$CLAUDEBOOST_HOME/scripts/compaction-save.py"; fi'
)

SIMPLE = '"$CLAUDEBOOST_PYTHON" "$CLAUDEBOOST_HOME/scripts/session-primer.py"'


@pytest.fixture(scope="module")
def install_mod():
    spec = importlib.util.spec_from_file_location(
        "cr_install", REPO / "clean-rag" / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_simple_command_is_still_wrapped(install_mod):
    """The wrapper must keep doing its job on the form it was written for."""
    out = install_mod._wrap_command(SIMPLE, runner=RUNNER)
    assert "hook-run.py" in out
    assert out.endswith('"$CLAUDEBOOST_HOME/scripts/session-primer.py"')


def test_a_fallback_chain_is_left_alone(install_mod):
    out = install_mod._wrap_command(FALLBACK, runner=RUNNER)
    assert out == FALLBACK, "a compound shell command must not be rewritten"


def test_the_corrupt_form_is_never_produced(install_mod):
    out = install_mod._wrap_command(FALLBACK, runner=RUNNER)
    assert f'if "{RUNNER}" command -v' not in out
    assert "hook-run.py" not in out


def test_wrapping_is_idempotent(install_mod):
    once = install_mod._wrap_command(SIMPLE, runner=RUNNER)
    assert install_mod._wrap_command(once, runner=RUNNER) == once


def test_an_already_mangled_command_is_repaired(install_mod):
    """
    Repair matters as much as prevention.

    _wrap_command declines anything already containing hook-run.py, so without
    an explicit repair a corrupted registration survives every re-install.
    """
    mangled = FALLBACK.replace("if command -v", f'if "{RUNNER}" command -v', 1)
    assert f'if "{RUNNER}" command -v' in mangled

    fixed = install_mod._unwrap_mangled(mangled, runner=RUNNER)
    assert fixed == FALLBACK
    assert install_mod._unwrap_mangled(fixed, runner=RUNNER) == FALLBACK


def test_the_repaired_command_actually_runs(install_mod):
    """Shell-parse the repaired form, rather than trusting it looks right."""
    mangled = FALLBACK.replace("if command -v", f'if "{RUNNER}" command -v', 1)
    fixed = install_mod._unwrap_mangled(mangled, runner=RUNNER)
    r = subprocess.run(["/bin/sh", "-n", "-c", fixed], capture_output=True, text=True)
    assert r.returncode == 0, f"repaired command is not valid shell: {r.stderr}"
