"""The console opens once per clean-rag home, and never refuses to open.

Two properties pull against each other here and both matter. Running
`server_ctl.py start` repeatedly must not stack console windows, and closing
the console window must leave the very next launch able to open a new one. A
guard that only gets the first right is the one that strands someone with no
console, so most of these tests attack the second.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_CLEAN_RAG_HOME = Path(__file__).resolve().parent.parent
if str(_CLEAN_RAG_HOME) not in sys.path:
    sys.path.insert(0, str(_CLEAN_RAG_HOME))

from cli import single_instance  # noqa: E402

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="the guard is a Windows named mutex"
)


@pytest.fixture(autouse=True)
def _fresh_module_state():
    """Each test starts with no held handle.

    The handle is a module global on purpose, so leaving one set would make
    the next test read state from this one.
    """
    single_instance._held_handle = None
    yield
    single_instance._held_handle = None


def _unique_home(tmp_path: Path, name: str) -> Path:
    home = tmp_path / name
    home.mkdir()
    return home


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def test_two_checkouts_get_different_mutex_names(tmp_path):
    """Mutant 3: a hardcoded name would make one checkout block the other."""
    a = single_instance.mutex_name(_unique_home(tmp_path, "checkout-a"))
    b = single_instance.mutex_name(_unique_home(tmp_path, "checkout-b"))
    assert a != b


def test_the_same_home_always_gets_the_same_name(tmp_path):
    home = _unique_home(tmp_path, "stable")
    assert single_instance.mutex_name(home) == single_instance.mutex_name(str(home))


def test_name_is_session_scoped_not_machine_wide(tmp_path):
    """Global\\ would let one signed in user block another's console."""
    name = single_instance.mutex_name(_unique_home(tmp_path, "scope"))
    assert name.startswith("Local\\")
    assert "Global\\" not in name


def test_name_has_no_extra_backslash(tmp_path):
    """Windows rejects a mutex name with a backslash past the namespace prefix."""
    name = single_instance.mutex_name(_unique_home(tmp_path, "slashes"))
    assert name.count("\\") == 1


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------

@windows_only
def test_first_call_reports_not_running(tmp_path):
    assert single_instance.already_running(_unique_home(tmp_path, "first")) is False


@windows_only
def test_second_call_sees_the_first(tmp_path):
    """Mutant 1: checking `if not handle` instead of GetLastError fails here.

    CreateMutexW hands back a valid handle whether or not the mutex already
    existed, so a guard that only tests the handle never detects anything.
    """
    home = _unique_home(tmp_path, "second")
    assert single_instance.already_running(home) is False
    assert single_instance.already_running(home) is True


@windows_only
def test_a_different_home_is_unaffected(tmp_path):
    a = _unique_home(tmp_path, "home-a")
    b = _unique_home(tmp_path, "home-b")
    assert single_instance.already_running(a) is False
    assert single_instance.already_running(b) is False


@windows_only
def test_the_handle_is_kept_so_the_mutex_outlives_the_call(tmp_path):
    """A handle dropped at return would release the mutex and guard nothing."""
    single_instance.already_running(_unique_home(tmp_path, "held"))
    assert single_instance._held_handle


@windows_only
def test_the_losing_call_does_not_overwrite_the_held_handle(tmp_path):
    home = _unique_home(tmp_path, "nosteal")
    single_instance.already_running(home)
    first = single_instance._held_handle
    single_instance.already_running(home)
    assert single_instance._held_handle == first


# ---------------------------------------------------------------------------
# Fail open. Every one of these must answer "no console is running".
# ---------------------------------------------------------------------------

def test_non_windows_never_reports_running(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    home = _unique_home(tmp_path, "posix")
    assert single_instance.already_running(home) is False
    assert single_instance.already_running(home) is False


@windows_only
def test_a_raising_kernel32_fails_open(tmp_path, monkeypatch):
    """Mutant 2: `except Exception: return True` would strand the user."""
    import ctypes

    def boom(*a, **k):
        raise OSError("kernel32 unavailable")

    monkeypatch.setattr(ctypes, "WinDLL", boom)
    assert single_instance.already_running(_unique_home(tmp_path, "raise")) is False


@windows_only
def test_a_null_handle_fails_open(tmp_path, monkeypatch):
    import ctypes

    class _Kernel32:
        class CreateMutexW:
            argtypes = None
            restype = None

            def __call__(self, *a):
                return 0

        class CloseHandle:
            argtypes = None
            restype = None

            def __call__(self, *a):
                return 1

        def __init__(self):
            self.CreateMutexW = _Kernel32.CreateMutexW()
            self.CloseHandle = _Kernel32.CloseHandle()

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _Kernel32())
    assert single_instance.already_running(_unique_home(tmp_path, "null")) is False


@windows_only
def test_a_missing_symbol_fails_open(tmp_path, monkeypatch):
    import ctypes

    class _Empty:
        def __getattr__(self, name):
            raise AttributeError(name)

    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: _Empty())
    assert single_instance.already_running(_unique_home(tmp_path, "missing")) is False


def test_an_unresolvable_home_fails_open(monkeypatch):
    """Path.resolve raising must not take the console down with it."""
    def boom(self, *a, **k):
        raise OSError("no such path")

    monkeypatch.setattr(Path, "resolve", boom)
    assert single_instance.already_running("C:/nope") is False


# ---------------------------------------------------------------------------
# The sequence that breaks every marker file design
# ---------------------------------------------------------------------------

@windows_only
def test_closing_the_console_lets_the_next_one_open(tmp_path):
    """Close the window, then launch again. This must work.

    The mutex is released by Windows when the holding process ends, so a fresh
    process sees nothing. Simulated here by dropping the handle the way process
    teardown does, since a real second process cannot share this one's state.
    """
    import ctypes

    home = _unique_home(tmp_path, "reopen")
    assert single_instance.already_running(home) is False

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle(single_instance._held_handle)
    single_instance._held_handle = None

    assert single_instance.already_running(home) is False


@windows_only
def test_a_real_second_process_is_blocked_and_a_later_one_is_not(tmp_path):
    """The whole point, proven across real processes rather than in one.

    Two processes hold the mutex at once, so the second must see it. Once both
    have exited, a third must not, because nothing cleaned up and nothing had
    to.
    """
    import subprocess
    import textwrap

    home = _unique_home(tmp_path, "procs")
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(_CLEAN_RAG_HOME)!r})
        from cli.single_instance import already_running
        print("RUNNING" if already_running({str(home)!r}) else "FREE", flush=True)
        time.sleep(float(sys.argv[1]))
    """)

    holder = subprocess.Popen(
        [sys.executable, "-c", script, "6"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "FREE"

        second = subprocess.run(
            [sys.executable, "-c", script, "0"],
            capture_output=True, text=True, timeout=60,
        )
        assert second.stdout.strip() == "RUNNING", second.stderr
    finally:
        holder.kill()
        holder.wait(timeout=30)

    third = subprocess.run(
        [sys.executable, "-c", script, "0"],
        capture_output=True, text=True, timeout=60,
    )
    assert third.stdout.strip() == "FREE", third.stderr


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------

def test_console_main_checks_the_guard_before_starting_the_app():
    """Guarding after `ConsoleApp().run()` would guard nothing, since run blocks."""
    source = (_CLEAN_RAG_HOME / "cli" / "console.py").read_text(encoding="utf-8")
    body = source.split("def main()", 1)[1]
    assert body.index("already_running") < body.index("ConsoleApp().run()")


def test_console_imports_the_guard():
    source = (_CLEAN_RAG_HOME / "cli" / "console.py").read_text(encoding="utf-8")
    assert "from cli.single_instance import already_running" in source


def test_the_guard_module_needs_no_new_dependency():
    """ctypes and hashlib are stdlib, so requirements.txt stays put.

    Only import lines count. The module's prose names `tendo.singleton` as a
    design it deliberately rejected, and matching that would be matching the
    wrong thing.
    """
    source = (_CLEAN_RAG_HOME / "cli" / "single_instance.py").read_text(encoding="utf-8")
    imports = [
        line.strip() for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    assert imports, "no imports found, so this test would pass vacuously"
    for third_party in ("psutil", "filelock", "portalocker", "tendo", "pywin32", "win32api"):
        offenders = [line for line in imports if third_party in line]
        assert not offenders, offenders


def test_the_guard_imports_without_textual(monkeypatch):
    """console.py exits when textual is missing, so the guard must not need it."""
    monkeypatch.setitem(sys.modules, "textual", None)
    importlib.reload(single_instance)
    assert callable(single_instance.already_running)
