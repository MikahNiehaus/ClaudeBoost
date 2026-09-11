"""Tests for scripts/setup.py: the preflight must check the version it names.

The preflight row was labelled "Python 3.9+" while its check only asked
`shutil.which` whether an interpreter named python or python3 existed. It never
read a version, so a fresh install on 3.8 printed `[OK] Python 3.9+` and then
installed hooks that could not import at all. The label was the only thing
claiming a floor, and nothing enforced it.

3.9 is the documented floor in five user facing places: setup.py's own label,
install.bat, install.sh, uninstall.bat and uninstall.sh.

Nothing is mocked out of subprocess. A real interpreter shim on an isolated
PATH stands in for an old python, so the assertions are about what setup.py
printed after really running one.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, isolate_path_to

_spec = importlib.util.spec_from_file_location(
    "setup_preflight_test", SCRIPTS_DIR / "setup.py")
_setup = importlib.util.module_from_spec(_spec)
sys.modules["setup_preflight_test"] = _setup
_spec.loader.exec_module(_setup)


def _fake_interpreter(tmp_path: Path, name: str, body: str, exit_code: int = 0) -> Path:
    """An executable named `name` that prints `body` and exits `exit_code`."""
    shim_dir = tmp_path / f"bin_{name}"
    shim_dir.mkdir(exist_ok=True)
    if sys.platform == "win32":
        (shim_dir / f"{name}.cmd").write_text(
            f"@echo off\r\necho {body}\r\nexit /b {exit_code}\r\n", encoding="ascii")
    else:
        script = shim_dir / name
        script.write_text(
            f"#!/bin/sh\necho '{body}'\nexit {exit_code}\n", encoding="ascii")
        script.chmod(0o755)
    return shim_dir


def test_the_floor_the_message_names_is_the_floor_that_is_enforced() -> None:
    """The label and the comparison come from one constant, so they cannot drift.

    This is the actual defect: a hardcoded "Python 3.9+" string sitting next to
    a check that knew nothing about 3.9.
    """
    assert _setup.MIN_PYTHON_STR == "{}.{}".format(*_setup.MIN_PYTHON)
    assert _setup.MIN_PYTHON == (3, 9), (
        "the floor moved; update install.bat, install.sh, uninstall.bat and "
        "uninstall.sh, which all print it to the user as well"
    )


def test_interpreter_version_reads_a_real_version() -> None:
    """Against the interpreter running this test, which we already know."""
    assert _setup._interpreter_version(sys.executable) == sys.version_info[:2]


@pytest.mark.parametrize("body", ["not a version", "3", "3.9.1.2", ""])
def test_interpreter_version_reports_none_when_it_cannot_tell(
    tmp_path: Path, body: str
) -> None:
    """Unparseable output reads as "cannot confirm", never as a failure.

    A Windows Store python alias prints an advert and exits, and an interpreter
    behind a wrapper may print anything. Guessing a version from that would be
    worse than declining to, so these degrade to no finding.
    """
    shim = _fake_interpreter(tmp_path, "pyprobe", body)
    exe = next(shim.iterdir())
    assert _setup._interpreter_version(str(exe)) is None


def test_interpreter_version_reports_none_for_a_missing_binary(tmp_path: Path) -> None:
    assert _setup._interpreter_version(str(tmp_path / "definitely-not-here")) is None


def test_interpreter_version_ignores_output_from_a_probe_that_failed(
    tmp_path: Path,
) -> None:
    """A version printed alongside a nonzero exit is not a version.

    This is the Windows Store alias shape and the shape of any wrapper that
    prints a diagnostic and gives up. Trusting the text anyway would let a
    stub's output stand in for a real interpreter's.
    """
    shim = _fake_interpreter(tmp_path, "pybroken", "3.99", exit_code=1)
    exe = next(shim.iterdir())
    assert _setup._interpreter_version(str(exe)) is None


def test_preflight_refuses_when_the_running_interpreter_is_below_the_floor(
    monkeypatch, capsys
) -> None:
    """Installing hooks that cannot import is worse than not installing them.

    The failure would otherwise surface as a traceback on every Edit, above the
    hooks' own fail open handlers, with nothing naming the cause.
    """
    too_old = (_setup.MIN_PYTHON[0], _setup.MIN_PYTHON[1] - 1)
    monkeypatch.setattr(_setup.sys, "version_info", too_old + (0, "final", 0))

    assert _setup._check_python() is False

    out = capsys.readouterr().out
    assert "[ERROR]" in out
    assert "{}.{}".format(*too_old) in out, (
        f"the message must name the version it actually found: {out!r}")
    assert _setup.MIN_PYTHON_STR in out


def test_preflight_accepts_the_floor_itself(monkeypatch, capsys) -> None:
    """3.9 is supported, not merely close to supported.

    The comparison has to be `<`, never `<=`. Getting that boundary wrong turns
    the check into a refusal of the exact version every install script tells the
    user to go and install, which is the most confusing failure available here.
    """
    monkeypatch.setattr(
        _setup.sys, "version_info", _setup.MIN_PYTHON + (0, "final", 0))

    assert _setup._check_python() is True
    assert "[ERROR]" not in capsys.readouterr().out


def test_preflight_passes_and_names_the_version_it_found(monkeypatch, capsys) -> None:
    isolate_path_to(monkeypatch, SCRIPTS_DIR)  # no python* shims on PATH

    assert _setup._check_python() is True

    out = capsys.readouterr().out
    assert "[ERROR]" not in out
    assert "{}.{}".format(*sys.version_info[:2]) in out, (
        f"a passing check should still report what it saw: {out!r}")


def test_an_old_path_fallback_warns_but_does_not_refuse(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The hook command line prefers $CLAUDEBOOST_PYTHON and only falls back to
    a PATH name when that is unset, so an old fallback is a warning.

    Refusing here would block an otherwise correct install over an interpreter
    the hooks will normally never reach.
    """
    old = "{}.{}".format(_setup.MIN_PYTHON[0], _setup.MIN_PYTHON[1] - 1)
    isolate_path_to(monkeypatch, _fake_interpreter(tmp_path, "python3", old))

    assert _setup._check_python() is True

    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "python3" in out
    assert old in out
    assert "[ERROR]" not in out


def test_a_current_path_fallback_says_nothing(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """No warning for an interpreter that meets the floor, so the warning above
    means something when it appears."""
    current = "{}.{}".format(*sys.version_info[:2])
    isolate_path_to(monkeypatch, _fake_interpreter(tmp_path, "python3", current))

    assert _setup._check_python() is True
    assert "[WARN]" not in capsys.readouterr().out
