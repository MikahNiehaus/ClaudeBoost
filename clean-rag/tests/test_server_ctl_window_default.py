"""The server starts with no window unless CLEAN_RAG_HEADED=1 asks for one.

Neither branch of this choice was tested before. That mattered, because the
default was reversed on 2026-09-18 and the whole edit is "which boolean feeds
which branch", which is precisely the shape of change that silently wires the
wrong block to the wrong flag and still runs fine on the machine that made it.

The flags are asserted rather than a real process observed, because the only
honest observation of a window is a human looking at a screen. What can be
checked mechanically is the contract handed to CreateProcess, and that is what
these do.

Why the specific flags, from Microsoft's process creation flags reference:

  CREATE_NO_WINDOW  "is ignored ... if it is used with either
                    CREATE_NEW_CONSOLE or DETACHED_PROCESS"
  DETACHED_PROCESS  "the new process does not inherit its parent's console",
                    and "cannot be used with CREATE_NEW_CONSOLE"

So DETACHED_PROCESS, not CREATE_NO_WINDOW, is what gives a server that has no
window AND outlives its launcher. A test that accepted either would not catch
the wrong one being used.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "server_ctl_window_test", str(CLEAN_RAG / "cli" / "server_ctl.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Recorder:
    """Stands in for subprocess.Popen and keeps what it was called with."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        # argv is kept as well as the keywords, because cmd_start now spawns
        # twice: the server, then cli/console.py in its own window. Without the
        # argv there is no way to tell which set of flags belongs to which, and
        # reading the last call silently started asserting on the console.
        self.calls.append({"argv": args[0] if args else [], **kwargs})
        self.pid = 4242
        return self


@pytest.fixture()
def ctl(tmp_path, monkeypatch):
    mod = _load()
    # Never touch the real port, the real state directory, or a real process.
    #
    # _CLEAN_RAG_HOME stays real on purpose. Repointing it at tmp_path breaks
    # _state_dir(), which imports server.config from that path, and the only
    # things the real value feeds here are Popen's cwd and the script path,
    # neither of which is used once Popen is a recorder.
    monkeypatch.setattr(mod, "_port_in_use", lambda port: False)
    monkeypatch.setattr(mod, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(mod, "_server_python", lambda: sys.executable)
    rec = _Recorder()
    monkeypatch.setattr(mod.subprocess, "Popen", rec)
    return mod, rec


def _server_calls(rec):
    """Only the spawns of the server itself, never the console window."""
    out = []
    for call in rec.calls:
        argv = call.get("argv") or []
        script = str(argv[-1]) if argv else ""
        if script.replace("\\", "/").endswith("server/__main__.py"):
            out.append(call)
    return out


def _flags(rec):
    assert rec.calls, "cmd_start never spawned anything"
    server = _server_calls(rec)
    assert server, (
        "cmd_start spawned something, but none of it was the server. "
        f"argv seen: {[c.get('argv') for c in rec.calls]}"
    )
    return server[-1].get("creationflags", 0)


def _console_calls(rec):
    out = []
    for call in rec.calls:
        argv = call.get("argv") or []
        script = str(argv[-1]) if argv else ""
        if script.replace("\\", "/").endswith("cli/console.py"):
            out.append(call)
    return out


@pytest.mark.skipif(sys.platform != "win32", reason="creationflags are Windows only")
def test_no_window_by_default(ctl, monkeypatch):
    mod, rec = ctl
    monkeypatch.delenv("CLEAN_RAG_HEADED", raising=False)
    mod.cmd_start(None)

    flags = _flags(rec)
    assert flags & subprocess.DETACHED_PROCESS, (
        "the default must detach, or the server dies with whatever launched it"
    )
    assert not (flags & subprocess.CREATE_NEW_CONSOLE), (
        "the default opened a console window, which is the thing this change removed"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="creationflags are Windows only")
def test_headed_opens_a_console(ctl, monkeypatch):
    mod, rec = ctl
    monkeypatch.setenv("CLEAN_RAG_HEADED", "1")
    mod.cmd_start(None)

    flags = _flags(rec)
    assert flags & subprocess.CREATE_NEW_CONSOLE, "CLEAN_RAG_HEADED=1 gave no window"
    assert not (flags & subprocess.DETACHED_PROCESS), (
        "DETACHED_PROCESS and CREATE_NEW_CONSOLE are mutually exclusive per "
        "Microsoft's own doc, so CreateProcess would reject this pair"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="creationflags are Windows only")
def test_only_the_literal_value_1_asks_for_a_window(ctl, monkeypatch):
    """A stale or empty value must not silently bring the window back."""
    mod, rec = ctl
    for value in ("", "0", "false", "true", "yes"):
        monkeypatch.setenv("CLEAN_RAG_HEADED", value)
        mod.cmd_start(None)
        assert not (_flags(rec) & subprocess.CREATE_NEW_CONSOLE), (
            f"CLEAN_RAG_HEADED={value!r} opened a window; only '1' should"
        )


@pytest.mark.skipif(sys.platform != "win32", reason="creationflags are Windows only")
def test_the_old_variable_no_longer_does_anything(ctl, monkeypatch):
    """CLEAN_RAG_HEADLESS is gone. Someone with it still set in their shell
    must not get behaviour that silently contradicts its name."""
    mod, rec = ctl
    monkeypatch.delenv("CLEAN_RAG_HEADED", raising=False)
    monkeypatch.setenv("CLEAN_RAG_HEADLESS", "1")
    mod.cmd_start(None)
    assert _flags(rec) & subprocess.DETACHED_PROCESS

    rec.calls.clear()
    monkeypatch.setenv("CLEAN_RAG_HEADLESS", "0")
    mod.cmd_start(None)
    assert _flags(rec) & subprocess.DETACHED_PROCESS, (
        "CLEAN_RAG_HEADLESS=0 changed the outcome, so the old name is still "
        "wired to something"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="the POSIX branch")
def test_posix_sends_output_to_devnull_unless_headed(ctl, monkeypatch):
    mod, rec = ctl
    monkeypatch.delenv("CLEAN_RAG_HEADED", raising=False)
    mod.cmd_start(None)
    assert rec.calls[-1].get("stdout") == subprocess.DEVNULL
    assert rec.calls[-1].get("start_new_session") is True

    monkeypatch.setenv("CLEAN_RAG_HEADED", "1")
    mod.cmd_start(None)
    assert rec.calls[-1].get("stdout") is None, "headed should inherit the terminal"


# ---------------------------------------------------------------------------
# The console UI comes up with the server.
#
# It never did before. server_ctl.py had no reference to cli/console.py at all,
# so the UI only existed if someone ran a second command by hand, and the
# windowless server meant indexing was otherwise invisible. The gap was real
# rather than a half built switch: runragserver.bat printed the console command
# as a suggestion instead of running it.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NEW_CONSOLE is Windows only")
def test_the_console_comes_up_with_the_server(ctl, monkeypatch):
    mod, rec = ctl
    monkeypatch.delenv("CLEAN_RAG_HEADED", raising=False)
    monkeypatch.delenv("CLEAN_RAG_CONSOLE", raising=False)
    mod.cmd_start(None)

    console = _console_calls(rec)
    assert console, "starting the server did not open the console UI"
    flags = console[-1].get("creationflags", 0)
    assert flags & subprocess.CREATE_NEW_CONSOLE, (
        "the console was spawned without a window, so a Textual app has no "
        "terminal to draw on and dies immediately"
    )
    assert not (flags & subprocess.DETACHED_PROCESS), (
        "DETACHED_PROCESS cannot be combined with CREATE_NEW_CONSOLE per "
        "Microsoft's process creation flags reference, so CreateProcess would "
        "reject this pair"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="CREATE_NEW_CONSOLE is Windows only")
def test_the_server_still_has_no_window_when_the_console_opens(ctl, monkeypatch):
    """The console gets the window. The server must still not have one.

    This is the pair that would silently go wrong: giving the server a console
    to make the UI appear brings back the 2026-09-18 failure where closing the
    window killed the server.
    """
    mod, rec = ctl
    monkeypatch.delenv("CLEAN_RAG_HEADED", raising=False)
    monkeypatch.delenv("CLEAN_RAG_CONSOLE", raising=False)
    mod.cmd_start(None)

    assert _flags(rec) & subprocess.DETACHED_PROCESS
    assert not (_flags(rec) & subprocess.CREATE_NEW_CONSOLE)


def test_console_zero_turns_it_off(ctl, monkeypatch):
    """Automation and CI set this. A test run must not spawn terminals."""
    mod, rec = ctl
    monkeypatch.setenv("CLEAN_RAG_CONSOLE", "0")
    mod.cmd_start(None)
    assert not _console_calls(rec), "CLEAN_RAG_CONSOLE=0 still opened a window"
    assert _server_calls(rec), "turning the console off also stopped the server"


def test_a_console_that_cannot_start_does_not_stop_the_server(ctl, monkeypatch):
    """A headless box, a missing terminal or a missing textual must not matter.

    The server is the thing that has to come up. Verified by making the console
    spawn raise for real rather than by reading the try/except.
    """
    mod, rec = ctl
    monkeypatch.delenv("CLEAN_RAG_CONSOLE", raising=False)

    real = rec

    def explode(*args, **kwargs):
        argv = args[0] if args else []
        script = str(argv[-1]) if argv else ""
        if script.replace("\\", "/").endswith("cli/console.py"):
            raise OSError("no console subsystem")
        return real(*args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "Popen", explode)
    mod.cmd_start(None)

    assert _server_calls(rec), "a failing console prevented the server from starting"


def test_starting_an_already_running_server_still_opens_the_console(ctl, monkeypatch):
    """Asking to start a live server is usually someone wanting to see it.

    Being told 'already running' and given nothing to look at is the state the
    user reported, so the early return has to open the UI too.
    """
    mod, rec = ctl
    monkeypatch.setattr(mod, "_port_in_use", lambda port: True)
    monkeypatch.delenv("CLEAN_RAG_CONSOLE", raising=False)
    mod.cmd_start(None)

    assert not _server_calls(rec), "it started a second server on a live port"
    if sys.platform == "win32":
        assert _console_calls(rec), "no UI, and no server either, so nothing happened"
