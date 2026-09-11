"""Git output must survive a locale that cannot represent it.

`subprocess.run(..., text=True)` with no `encoding=` decodes the child's output
with `locale.getpreferredencoding(False)`. That is cp1252 on a Western locale
Windows install and ascii under `LC_ALL=C` on POSIX, and neither can represent
most of what turns up in a real diff.

The failure is quiet in a way that matters. The decode runs on subprocess's
background reader thread, so the `UnicodeDecodeError` never reaches the caller:
`subprocess.run` returns normally with `returncode == 0` and `stdout` set to
None. verifier-gate then calls `.splitlines()` on None, the AttributeError lands
on the outermost fail open `sys.exit(0)`, and the gate stops nudging with no
way to tell that apart from having nothing to nudge about.

There is a second, quieter half. When every byte happens to be mapped by the
wrong codec (cp1252 maps all of U+041F's UTF-8 bytes, for instance) nothing
raises at all and the caller silently gets mojibake, which then feeds
high_stakes.scan_diff as if it were the real diff text.

The fix at each call site is an explicit `encoding="utf-8", errors="replace"`,
matching what this codebase already does for file reads and for stdout, and
what file_scan._git_check_ignore already does by decoding bytes itself. An
undecodable byte now becomes U+FFFD in the line rather than losing the whole
stream: these call sites only pattern match git's own ASCII framing ("+++ b/",
a leading "+", the two status columns), so a replacement character inside a
path or a content line costs nothing they read.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[1] / "hooks"

# U+0441 encodes to D1 81 in UTF-8, and 0x81 is one of the five bytes cp1252
# leaves undefined (0x81, 0x8D, 0x8F, 0x90, 0x9D). Picking a character whose
# bytes cp1252 happens to map would exercise the mojibake path instead and
# never raise, which is how this class hides.
UNDECODABLE_IN_CP1252 = "сход"

_ENV_ALLOWLIST = frozenset({
    "PATH", "PATHEXT", "COMSPEC", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR",
    "TEMP", "TMP", "TMPDIR", "PYTHONHOME",
})


def hostile_env() -> dict:
    """A declared environment whose preferred encoding cannot hold the payload.

    Built from an allowlist rather than from os.environ, so an ambient
    PYTHONUTF8=1 on the developer's machine cannot turn this test into a no-op
    that still passes. PYTHONUTF8=0 is set explicitly for the same reason and
    because Python 3.15 turns UTF-8 mode on by default; LC_ALL=C is what makes
    POSIX pick ascii, since cp1252 already covers Windows.
    """
    env = {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOWLIST}
    env["PYTHONUTF8"] = "0"
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_AUTHOR_NAME"] = env["GIT_COMMITTER_NAME"] = "test"
    env["GIT_AUTHOR_EMAIL"] = env["GIT_COMMITTER_EMAIL"] = "test@example.com"
    return env


@pytest.fixture
def repo_with_wide_diff(tmp_path: Path) -> Path:
    """A git repo whose single uncommitted change adds a line git must emit raw."""
    env = hostile_env()

    def git(*args: str) -> subprocess.CompletedProcess:
        proc = subprocess.run(["git", "-C", str(tmp_path), *args],
                              capture_output=True, env=env, timeout=30)
        assert proc.returncode == 0, (args, proc.stderr[:400])
        return proc

    if not subprocess.run(["git", "--version"], capture_output=True).returncode == 0:
        pytest.skip("git is not available")

    git("init", "-q")
    git("config", "core.quotepath", "false")
    sample = tmp_path / "sample.py"
    sample.write_text("x = 1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    sample.write_text(f"x = 1\ny = '{UNDECODABLE_IN_CP1252}'\n", encoding="utf-8")
    return tmp_path


def _diff_via_subprocess(repo: Path) -> tuple[int, str, str]:
    """Run verifier-gate._diff in a child process under the hostile environment.

    A child rather than an in process call, because the decode is chosen from
    the interpreter's own locale at startup and cannot be changed afterwards.
    """
    driver = repo / "_read_diff.py"
    driver.write_text(
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('vg', {str(HOOKS / 'verifier-gate.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules['vg'] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "added, paths = mod._diff(sys.argv[1])\n"
        "sys.stdout.buffer.write(json.dumps({'added': added, 'paths': paths}).encode('utf-8'))\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(driver), str(repo)],
        capture_output=True, env=hostile_env(), timeout=120,
    )
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace"),
            proc.stderr.decode("utf-8", "replace"))


def test_diff_reader_survives_a_line_the_locale_cannot_decode(
    repo_with_wide_diff: Path,
) -> None:
    """The added line comes back instead of the reader collapsing to None.

    Before the explicit encoding, `_diff` returned ([], []) here: stdout was
    None, `.splitlines()` raised AttributeError, and the gate went quiet.
    """
    import json

    returncode, stdout, stderr = _diff_via_subprocess(repo_with_wide_diff)
    assert returncode == 0, f"driver failed:\n{stderr}"
    assert "UnicodeDecodeError" not in stderr, stderr

    result = json.loads(stdout)
    assert result["paths"] == ["sample.py"], result
    assert any("y = " in line for line in result["added"]), result
    assert UNDECODABLE_IN_CP1252 in "".join(result["added"]), (
        "the line was found but its text was mangled, so the decode fell back "
        f"to the locale codec instead of utf-8: {result['added']}"
    )


@pytest.fixture
def repo_under_a_wide_path(tmp_path: Path) -> Path:
    """A repo whose own directory name, and one tracked filename, are wide.

    This is what actually reaches auto-test-gate. `git status --porcelain` does
    not print the branch name unless asked with -b, and `git rev-parse
    --show-toplevel` prints a path, so a wide branch name never gets near
    either. A wide path does: `--show-toplevel` echoes it back, and a wide
    filename reaches --porcelain whenever core.quotepath is false, which is a
    common setting rather than an exotic one. A checkout under a user account
    whose name is not ASCII hits the first one with no configuration at all.
    """
    env = hostile_env()
    root = tmp_path / f"проект-{UNDECODABLE_IN_CP1252}"
    root.mkdir()

    def git(*args: str) -> None:
        proc = subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, env=env, timeout=30)
        assert proc.returncode == 0, (args, proc.stderr[:400])

    git("init", "-q")
    git("config", "core.quotepath", "false")
    (root / "seed.py").write_text("x = 1\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    (root / f"модуль-{UNDECODABLE_IN_CP1252}.py").write_text("y = 2\n", encoding="utf-8")
    return root


def test_test_gate_survives_a_repo_path_the_locale_cannot_decode(
    repo_under_a_wide_path: Path,
) -> None:
    """auto-test-gate reads git the same way, so the same None stdout reaches
    _git_root and _code_changed, and the gate skips a turn that did change code."""
    env = hostile_env()
    driver = repo_under_a_wide_path / "_read_status.py"
    driver.write_text(
        "import importlib.util, json, sys\n"
        f"spec = importlib.util.spec_from_file_location('atg', {str(HOOKS / 'auto-test-gate.py')!r})\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "sys.modules['atg'] = mod\n"
        "spec.loader.exec_module(mod)\n"
        "root = mod._git_root(sys.argv[1])\n"
        "sys.stdout.buffer.write(json.dumps(\n"
        "    {'root_found': root is not None, 'code_changed': mod._code_changed(sys.argv[1])}\n"
        ").encode('utf-8'))\n",
        encoding="utf-8",
    )
    proc = subprocess.run([sys.executable, str(driver), str(repo_under_a_wide_path)],
                          capture_output=True, env=env, timeout=120)
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, stderr
    assert "UnicodeDecodeError" not in stderr, stderr

    import json
    result = json.loads(proc.stdout.decode("utf-8", "replace"))
    assert result["root_found"], (
        "`git rev-parse --show-toplevel` decoded to None, so the gate cannot "
        "locate the repo it was asked to test"
    )
    assert result["code_changed"], (
        "the new .py file was not seen, so `git status --porcelain` decoded to "
        "None and the test gate would skip a turn that really did change code"
    )
