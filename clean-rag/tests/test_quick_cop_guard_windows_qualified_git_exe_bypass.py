"""quick-cop-bash-guard.py tokenizes the padded command with a single call to
`shlex.split(padded)`, which runs in POSIX mode. POSIX mode treats a backslash
as an escape character, so a Windows path like
`C:\\Program Files\\Git\\bin\\git.exe` is not read back as separate path
segments containing the word "git" -- the backslashes are consumed as escapes
and the segments are fused: `shlex.split(r'C:\\Program Files\\Git\\bin\\git.exe push')`
produces `['C:Program', 'FilesGitbingit.exe', 'push', ...]`, and neither token
equals "git" or "git.exe" once `_binary_name()` strips a trailing ".exe" and a
path separator. `_check_subcommand_chain()` never recognises the invocation as
git at all, so `git push`, `git commit`, or any other blocked subcommand runs
straight through quick-cop's read-only cage when it is spelled with a
backslash-qualified Windows path to git.exe -- exactly the shape a real
invocation takes on the platform this project mainly runs on.

verify-loop-git-guard.py already fixed this exact class for its own
_tokenize(): it walks BOTH a POSIX and a non-POSIX shlex reading of the padded
command, because non-POSIX mode keeps backslashes literal and recovers "git"
from the fused path. Its own module docstring documents the identical
`C:\\Program Files\\Git\\bin\\git.exe commit` example. quick-cop-bash-guard.py
was never given the same second reading, so the two sibling guards diverge on
the exact same input: verify-loop-git-guard.py blocks it, quick-cop-bash-guard.py
allows it.
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
        r"C:\Program Files\Git\bin\git.exe push origin main",
        r"C:\Program Files\Git\bin\git.exe push --force origin main",
        r"C:\Program Files\Git\bin\git.exe commit -am x",
        r"C:\Program Files\Git\cmd\git.exe push origin main",
    ],
)
def test_a_backslash_qualified_windows_git_exe_path_is_not_allowed_to_mutate(command):
    """Every one of these really pushes or commits when actually run. The
    guard's own message says quick-cop is read only and must never mutate git
    state; a fully qualified Windows path to git.exe must not be a way around
    that."""
    result = _run(command)
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a git write via a backslash-qualified "
        f"Windows git.exe path (exit {result.returncode}): {command!r}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_a_backslash_qualified_windows_git_exe_path_still_allows_read_only_git():
    """The other side of it: quick-cop still needs plain read-only git to work
    through a fully qualified Windows path."""
    result = _run(r"C:\Program Files\Git\bin\git.exe status")
    assert result.returncode == 0, (
        f"exit {result.returncode} for read-only git via a qualified path\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_a_reading_that_will_not_parse_is_refused_rather_than_half_judged():
    r"""Reading both ways is only safe if a failed reading still counts.

    A trailing backslash makes the POSIX reading raise ("No escaped
    character") while the backslash-preserving reading parses fine. That
    surviving reading keeps quotes attached to their token, so `"git"` is not
    the word "git" to it and the push goes unseen -- yet a real shell strips
    those quotes and runs git. Judging only the reading that survived hands
    back "no blocked subcommand found" on half the evidence. quick-cop fails
    closed, so a command it cannot fully read is refused instead.
    """
    result = _run('"git" push origin main \\')
    assert result.returncode == 2, (
        f"quick-cop-bash-guard.py allowed a git write whose structure it could "
        f"not fully read (exit {result.returncode})\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
