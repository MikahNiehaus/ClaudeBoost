"""Tests for scripts/claude_cli.py — resolving the Claude Code CLI.

Every script that shells out to `claude` goes through claude_cmd(), so the
contract it has to keep is narrow: hand back something subprocess can launch,
or hand back None. Never a name that only looks resolvable.

Resolving to claude.cmd is what a standard npm install gives you, and it makes
the second contract load bearing: CreateProcess starts a batch target by
running cmd.exe, so cmd.exe re-parses the command line and an argument can stop
being data. reject_unsafe_args is what says no to that, and the tests below run
a real shim to show which characters actually get through.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

from helpers import SCRIPTS_DIR, isolate_path_to

sys.path.insert(0, str(SCRIPTS_DIR))

from claude_cli import claude_cmd, is_batch_shim, reject_unsafe_args  # noqa: E402

WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows executable extensions")
POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX executable bit")


def test_returns_none_when_nothing_is_on_path(tmp_path, monkeypatch):
    empty = tmp_path / "empty_bin"
    empty.mkdir()
    isolate_path_to(monkeypatch, empty)

    assert claude_cmd() is None


@WINDOWS_ONLY
def test_returns_a_cmd_shim_that_subprocess_can_launch(tmp_path, monkeypatch):
    """The npm install case: claude.cmd and nothing else."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude.cmd").write_text("@echo off\r\necho 2.1.0\r\n", encoding="ascii")
    isolate_path_to(monkeypatch, bin_dir)

    cmd = claude_cmd()
    assert cmd is not None
    probe = subprocess.run(cmd + ["--version"], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stderr
    assert "2.1.0" in probe.stdout


@WINDOWS_ONLY
def test_prefers_a_real_exe_over_the_batch_shim(tmp_path, monkeypatch):
    """A native install skips the batch layer, so the .exe wins when present."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude.cmd").write_text("@echo off\r\n", encoding="ascii")
    (bin_dir / "claude.exe").write_bytes(b"MZ")  # never executed, only resolved
    isolate_path_to(monkeypatch, bin_dir)

    cmd = claude_cmd()
    assert cmd is not None
    assert cmd[0].lower().endswith("claude.exe"), cmd


@WINDOWS_ONLY
def test_never_returns_the_extensionless_npm_script(tmp_path, monkeypatch):
    """npm drops a `claude` shell script beside claude.cmd on Windows.

    CreateProcess cannot start it — handing it to subprocess raises
    OSError [WinError 193] rather than launching anything. shutil.which("claude")
    has matched it on the 3.12 line (python/cpython#109590), so asking for the
    bare name is not safe. With only the script present the answer is None, and
    the caller degrades to "CLI not found" instead of crashing.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("#!/bin/sh\nexec node index.js\n", encoding="ascii")
    isolate_path_to(monkeypatch, bin_dir)

    assert claude_cmd() is None


@POSIX_ONLY
def test_returns_the_executable_on_posix(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe = bin_dir / "claude"
    exe.write_text("#!/bin/sh\necho 2.1.0\n", encoding="ascii")
    exe.chmod(0o755)
    isolate_path_to(monkeypatch, bin_dir)

    cmd = claude_cmd()
    assert cmd == [str(exe)]


@POSIX_ONLY
def test_ignores_a_non_executable_file_on_posix(tmp_path, monkeypatch):
    """A readable-but-not-executable `claude` is not a CLI."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").write_text("not executable\n", encoding="ascii")
    os.chmod(bin_dir / "claude", 0o644)
    isolate_path_to(monkeypatch, bin_dir)

    assert claude_cmd() is None


# ---------------------------------------------------------------------------
# Refusing arguments a batch shim would re-parse (CVE-2024-24576, BatBadBut).
# ---------------------------------------------------------------------------


def test_is_batch_shim_recognises_the_targets_that_go_through_cmd_exe():
    assert is_batch_shim(r"C:\npm\claude.cmd")
    assert is_batch_shim(r"C:\npm\CLAUDE.BAT")
    assert not is_batch_shim(r"C:\Program Files\claude.exe")
    assert not is_batch_shim("/usr/local/bin/claude")


@pytest.mark.parametrize(
    "payload",
    [
        'x" & whoami & rem ',   # closes the quoted region: the reported break out
        "x&whoami",             # no whitespace, so subprocess leaves it unquoted
        "x|whoami",
        "x>out.txt",
        "x^&whoami",
        "%USERNAME%",           # expands to the real value before the CLI sees it
        "!USERNAME!",           # same, under a shim with delayed expansion on
        "line one\nline two",   # silently truncates the argument
    ],
)
def test_refuses_an_argument_cmd_exe_would_reparse(payload):
    with pytest.raises(ValueError, match="batch shim"):
        reject_unsafe_args([r"C:\npm\claude.cmd"], ["-p", payload])


def test_allows_ordinary_text_through_to_a_batch_shim():
    """The refusal has to be narrow enough that normal arguments still run.

    chat-watcher's own system prompt is the case that matters: it carries
    apostrophes, commas and a pair of parentheses, none of which survived as
    anything but literal text when measured against a real shim.
    """
    reject_unsafe_args(
        [r"C:\npm\claude.cmd"],
        ["-p", "--model", "claude-haiku-4-5-20251001",
         "If the question is a test ('are you there', 'hello'), confirm it."],
    )


def test_a_real_executable_needs_no_refusal():
    """No cmd.exe in the launch path means no second parser to defend against.

    This is also the whole POSIX story, and why the guard does not degrade it.
    """
    reject_unsafe_args([r"C:\Program Files\claude.exe"], ['x" & whoami'])
    reject_unsafe_args(["/usr/local/bin/claude"], ['x" & whoami'])


def test_no_cli_resolved_is_not_a_refusal():
    reject_unsafe_args([], ['x" & whoami'])


@WINDOWS_ONLY
def test_every_refused_character_really_does_break_out_of_a_shim(tmp_path, monkeypatch):
    """The reject set is measured, not asserted from a specification.

    A guard justified only by reasoning drifts into rejecting things that were
    always safe. Each payload here runs against a throwaway shim and writes a
    marker file if, and only if, it executed as a command of its own. The
    marker is the entire payload: nothing else is written anywhere.
    """
    shim = tmp_path / "claude.cmd"
    shim.write_text("@echo off\r\necho ARGS: %*\r\n", encoding="ascii")
    isolate_path_to(monkeypatch, tmp_path)

    broke_out = []
    for label, template in [
        ("quote", 'x" & echo INJECTED>{marker} & rem '),
        ("ampersand", "x&echo.>{marker}"),
        ("pipe", "x|echo.>{marker}"),
        ("redirect", "x>{marker}"),
        ("caret", "x^&echo.>{marker}"),
    ]:
        marker = tmp_path / f"{label}.txt"
        payload = template.format(marker=marker)
        # Confirm the guard would have stopped this one before running it.
        with pytest.raises(ValueError):
            reject_unsafe_args([str(shim)], [payload])
        subprocess.run([str(shim), "-p", payload], capture_output=True,
                       text=True, timeout=30)
        if marker.exists():
            broke_out.append(label)

    assert broke_out == ["quote", "ampersand", "pipe", "redirect", "caret"], (
        "the reject set no longer matches what actually escapes a batch shim"
    )


@WINDOWS_ONLY
def test_the_prompt_survives_intact_on_stdin_when_argv_would_mangle_it(tmp_path, monkeypatch):
    """The alternative the guard points callers at has to actually work.

    Every payload the guard refuses in argv goes through stdin unchanged, which
    is why refusing costs no functionality.
    """
    seen = tmp_path / "seen_stdin.txt"
    shim = tmp_path / "claude.cmd"
    shim.write_text(f'@echo off\r\nfindstr "^" > "{seen}"\r\necho answered\r\n',
                    encoding="ascii")
    isolate_path_to(monkeypatch, tmp_path)

    payload = 'x" & whoami & rem  and %USERNAME% and x&y'
    result = subprocess.run([str(shim), "-p"], input=payload + "\n",
                            capture_output=True, text=True, timeout=30)

    assert result.stdout.strip() == "answered"
    assert seen.read_text().strip() == payload
