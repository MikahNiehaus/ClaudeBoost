"""quick-cop-bash-guard.py's own docstring says it fails closed by design,
per an explicit user requirement, and that "an unrecognized command is not
evidence it is safe." Its _check_subcommand_chain() walks shlex.split()
tokens looking for a blocked binary or git/package-manager subcommand.

The same shlex gap covered in
test_git_guard_unspaced_chaining_bypass.py applies here: shlex treats ';',
'|', and '&' as ordinary word characters when nothing whitespace-separates
them from the previous word, so `pytest;rm -rf important_dir` tokenizes as
one fused word ("pytest;rm") and a separate "-rf", never as the binary "rm"
quick-cop's own _BLOCKED_BINARIES set is checked against. quick-cop, which is
supposed to be incapable of deleting, moving, installing, or touching git
state at all, can be made to do every one of those with a single semicolon
and no space.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
GUARD = "quick-cop-bash-guard.py"

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR",
    "PYTHONHOME", "PYTHONIOENCODING", "PYTHONUTF8", "LANG", "LC_ALL",
})


def _hermetic_env() -> dict:
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}


def _bash(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


def _run(command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / GUARD)],
        input=_bash(command),
        capture_output=True,
        text=True,
        env=_hermetic_env(),
    )


@pytest.mark.parametrize(
    "command",
    [
        "pytest;rm -rf important_dir",
        "echo hi;git add secrets.txt",
        "echo hi;git commit -m x",
        "echo hi&git commit -m x",
        "true|npm install left-pad",
        "echo hi;mv real.json fake.json",
    ],
)
def test_unspaced_chaining_smuggles_a_blocked_mutation_past_quick_cop(command):
    """Every one of these mutates something -- deletes a directory, stages or
    commits in git, installs a package, moves a file -- exactly the class of
    action quick-cop's own docstring says it must never be able to do "even
    if this guard cannot name the exact command in advance." A single
    semicolon with no space is enough."""
    result = _run(command)
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a mutation through unspaced "
        f"chaining (exit {result.returncode}): {command!r}\n"
        f"stderr: {result.stderr}"
    )


def test_spaced_equivalent_is_still_caught():
    """Sanity: the identical mutation with a space before the semicolon is
    the shape the existing suite already covers. Pinned so a fix for the
    unspaced case cannot regress this one."""
    result = _run("pytest ; rm -rf important_dir")
    assert result.returncode == 2


@pytest.mark.parametrize("command", ["(rm -rf x)", "echo `rm -rf x`"])
def test_a_subshell_or_substitution_also_runs_the_mutation(command):
    """A semicolon is not the only thing a shell reads as the start of a new
    command, and each of these really deletes the directory."""
    result = _run(command)
    assert result.returncode == 2, (
        f"exit {result.returncode} for {command!r}\nstderr: {result.stderr}"
    )


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q",
        "python -m pytest -q;python -m pytest scripts/tests -q",
        "dotnet build;dotnet test",
        "git status;git diff",
        "grep -rn 'rm -rf' src/",
        'echo "rm -rf x"',
        r"find . -name '*.py' -exec grep -l foo {} \;",
    ],
)
def test_reading_a_separator_correctly_does_not_cost_quick_cops_real_job(command):
    """quick-cop still has to run the project's existing tests and read the
    tree. A blocked binary named inside a quoted string or escaped as an
    argument is not an invocation, and chaining two read only commands is
    not a mutation."""
    result = _run(command)
    assert result.returncode == 0, (
        f"exit {result.returncode} for {command!r}\nstderr: {result.stderr}"
    )
