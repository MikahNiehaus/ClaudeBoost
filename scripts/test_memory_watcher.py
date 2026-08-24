"""The watcher must name a large process without ever reading an argument.

Written because the watcher caught a process going 1.9 GB to 27 GB and all it
recorded was "python.exe", which identifies nothing on a machine running
several. The fix reads one token, the script path, and the risk it has to avoid
is reading the token after a flag, since that is where secrets live.

Run: python scripts/test_memory_watcher.py
"""

import importlib.util
import sys
from pathlib import Path

import psutil

_spec = importlib.util.spec_from_file_location(
    "mw", Path(__file__).resolve().parent / "memory-watcher.py"
)
mw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mw)


class _Proc:
    """Only what _script_of touches."""

    def __init__(self, argv=None, raises=None):
        self._argv, self._raises = argv, raises

    def cmdline(self):
        if self._raises:
            raise self._raises
        return self._argv


def test_names_the_script_of_an_interpreter():
    p = _Proc([r"C:\Python312\python.exe", r"C:\prj\ClaudeBoost\reindex.py"])
    assert mw._script_of(p) == r"C:\prj\ClaudeBoost\reindex.py"


def test_never_returns_the_value_that_follows_a_flag():
    """The whole safety property, asserted directly.

    A flag's value is where a secret lives. Skipping flags rather than consuming
    them in pairs means a miss lands on the next flag or on the script, never on
    a value.
    """
    secret = "AKIAIOSFODNN7EXAMPLE"
    for argv in (
        ["python.exe", "--api-key", secret, "run.py"],
        ["python.exe", "-p", secret, "run.py"],
        ["python.exe", "--token", secret],
    ):
        got = mw._script_of(_Proc(argv))
        assert got != secret, f"leaked the value after a flag: {argv} -> {got}"
        assert got in (None, "run.py"), f"unexpected token from {argv}: {got}"


def test_ignores_non_interpreters_entirely():
    """curl's first positional token is a URL, and a URL can carry credentials.

    The executable name already identifies a non interpreter, so no argument of
    one is read at all.
    """
    p = _Proc(["curl.exe", "https://user:hunter2@example.com/x"])
    assert mw._script_of(p) is None


def test_survives_a_process_that_will_not_answer():
    for exc in (psutil.AccessDenied(), psutil.NoSuchProcess(1), OSError()):
        assert mw._script_of(_Proc(raises=exc)) is None
    assert mw._script_of(_Proc([])) is None


def test_sample_identifies_only_above_the_threshold():
    """Small processes stay unidentified, so cmdline() is not called for them.

    That gate is the reason the watcher does not become part of the load it is
    measuring: on Windows cmdline() reads the target PEB through
    ReadProcessMemory, far heavier than name().
    """
    row = mw.sample()
    assert row["free_mb"] > 0 and row["top"], "sampler returned nothing usable"
    for e in row["top"]:
        assert {"pid", "name", "rss_mb"} <= set(e)
        if e["rss_mb"] < mw.IDENTIFY_ABOVE_MB:
            assert "script" not in e, (
                f"identified a process below the threshold: {e}"
            )
    # This process is an interpreter running this file, so pointing the
    # threshold at it must produce a script and that script must be this test.
    me = psutil.Process()
    got = mw._script_of(me)
    assert got and Path(got).name == Path(__file__).name, (
        f"expected this test file as the script, got {got!r}"
    )


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)
