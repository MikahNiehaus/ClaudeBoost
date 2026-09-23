"""Adversarial re-check findings against the protected-path hardening in
scripts/bash-guard.py. Written by bad-cop, not committed by the fix author.

Two real, ordinary-syntax bypasses of check_protected_paths survive the fix
that closed the nine cases scripts/tests/test_bash_guard_expanded_paths.py
already covers: bash array/associative-array expansion, and bash parameter
expansion with a default value. Both are confirmed against real Git Bash, not
assumed from reading the regex.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "bash-guard.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("bash_guard_recheck", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load_guard()


# subprocess PATH lookup for "bash" resolves to the Windows/WSL relay
# bash.exe on this machine, not Git Bash, and that relay fails outright with
# no WSL distro installed. Git Bash's own bash.exe is named explicitly so
# this proves real Git Bash semantics, the same shell the guard's own
# comments say this tree runs under.
_GIT_BASH = r"C:\Program Files\Git\usr\bin\bash.exe"


def _bash_expands_to(script: str) -> str:
    """What real Git Bash actually produces for `script`, proving the shell
    semantics the guard is supposed to be judging rather than assuming them.
    """
    result = subprocess.run([_GIT_BASH, "-c", script], capture_output=True,
                             text=True, timeout=10)
    return result.stdout.strip()


class TestArrayExpansionReachesAProtectedPath:
    """A shell array is an ordinary assignment (`arr=(...)`), and every
    reference to it is a variable reference the same way `$F` is. Neither
    _record_assignments nor _VAR_REF_RE recognises the array syntax, so none
    of it is resolved, and the unresolved word matches no protected pattern
    either. Confirmed against real Git Bash: every one of the four
    expansions below really does produce `scripts/bash-guard.py`.
    """

    @pytest.mark.parametrize("script", [
        "arr=(scripts/bash-guard.py); echo \"${arr[0]}\"",
        "arr=(scripts/bash-guard.py); echo \"$arr\"",
        "arr=(scripts/bash-guard.py); echo \"${arr[@]}\"",
        "declare -A m=([k]=scripts/bash-guard.py); echo \"${m[k]}\"",
        "arr[0]=scripts/bash-guard.py; echo \"${arr[0]}\"",
    ])
    def test_real_bash_resolves_the_array_reference_to_the_guard(self, script):
        assert _bash_expands_to(script) == "scripts/bash-guard.py"

    @pytest.mark.parametrize("command", [
        "arr=(scripts/bash-guard.py); rm ${arr[0]}",
        "arr=(scripts/bash-guard.py); rm $arr",
        "arr=(scripts/bash-guard.py); rm ${arr[@]}",
        "declare -A m=([k]=scripts/bash-guard.py); rm ${m[k]}",
        "arr[0]=scripts/bash-guard.py; rm ${arr[0]}",
    ])
    def test_the_guard_still_refuses_it(self, guard, command):
        """This is the failing assertion: today the guard allows every one
        of these, even though the write really lands on its own file."""
        assert guard.evaluate(command) is not None, (
            f"{command!r} deletes scripts/bash-guard.py in real bash "
            f"(see test_real_bash_resolves_the_array_reference_to_the_guard) "
            f"and the guard's own evaluate() returned None: unblocked."
        )


class TestParameterExpansionDefaultReachesAProtectedPath:
    """`${VAR:-default}`, `${VAR:+default}` and `${VAR-default}` are ordinary
    parameter expansion, not an exotic construct. When VAR is unset, bash
    substitutes the default text, which can be the guard's own path. Neither
    the whole word variable check nor _is_protected_path's anchored regexes
    survive the wrapper. The `:=` form is coincidentally caught, but only
    because _path_candidates splits on a literal '=' for `dd of=path`
    syntax, not because the guard understands `:=` semantics.
    """

    @pytest.mark.parametrize("script,expected", [
        ("unset X; echo \"${X:-scripts/bash-guard.py}\"", "scripts/bash-guard.py"),
        ("X=1; echo \"${X:+scripts/bash-guard.py}\"", "scripts/bash-guard.py"),
        ("unset Y; echo \"${Y-scripts/bash-guard.py}\"", "scripts/bash-guard.py"),
    ])
    def test_real_bash_resolves_the_default_to_the_guard(self, script, expected):
        assert _bash_expands_to(script) == expected

    @pytest.mark.parametrize("command", [
        "rm ${UNSET_VAR:-scripts/bash-guard.py}",
        "X=1; rm ${X:+scripts/bash-guard.py}",
        "rm ${UNSET_VAR2-scripts/bash-guard.py}",
    ])
    def test_the_guard_still_refuses_it(self, guard, command):
        assert guard.evaluate(command) is not None, (
            f"{command!r} deletes scripts/bash-guard.py in real bash when the "
            f"named variable is unset (X:+ fires because X IS set), and the "
            f"guard's own evaluate() returned None: unblocked."
        )
