"""The watcher must never run twice, and its launcher must never fail a session.

Both properties exist because the watcher is wired to SessionStart. A machine
routinely has several Claude sessions open, so without a guard each one starts
its own sampler: N times the CPU, all appending to one file, on a machine that
is already short of memory. The measuring tool becomes part of what it measures.

The launcher's exit code matters for a different reason. A SessionStart hook
that exits non-zero is a hook that can interfere with starting work, and a
memory sampler is diagnostics. Diagnostics must never be able to stop you
working, so every failure path here has to come back 0.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
WATCHER = SCRIPTS / "memory-watcher.py"
LAUNCHER = SCRIPTS / "memory-watcher-start.py"

psutil = pytest.importorskip("psutil")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def watcher():
    return _load("_mw_under_test", WATCHER)


def _live_watchers():
    """PIDs of real python processes running memory-watcher.py."""
    out = []
    for p in psutil.process_iter(["pid", "name"]):
        if Path(p.info["name"] or "").stem.lower() not in {"python", "pythonw", "py"}:
            continue
        try:
            argv = p.cmdline()
        except Exception:
            continue
        if any(Path(str(t)).name == "memory-watcher.py" for t in argv):
            out.append(p.info["pid"])
    return out


class TestAlreadyRunning:
    def test_never_reports_the_calling_process(self, watcher):
        # The check runs from inside the watcher itself, so counting itself
        # would make every start a no-op and nothing would ever sample.
        assert watcher.already_running() != os.getpid()

    def test_returns_none_or_a_live_pid(self, watcher):
        found = watcher.already_running()
        if found is None:
            assert not _live_watchers()
        else:
            assert isinstance(found, int)
            assert psutil.pid_exists(found)

    def test_agrees_with_an_independent_process_scan(self, watcher):
        # Two different ways of asking the same question must not disagree.
        assert (watcher.already_running() is not None) == bool(_live_watchers())


class TestLauncherAlwaysExitsZero:
    """Every failure path, because this runs at SessionStart."""

    def test_exits_zero_normally(self):
        r = subprocess.run([sys.executable, str(LAUNCHER)],
                           capture_output=True, text=True, timeout=90)
        assert r.returncode == 0, r.stderr

    def test_exits_zero_when_the_watcher_is_absent(self, tmp_path):
        # The branch-switch case: settings.json still points here, the script
        # is gone. Copy the launcher somewhere with no memory-watcher.py beside
        # it, which is exactly what that looks like.
        stand_in = tmp_path / "memory-watcher-start.py"
        stand_in.write_text(LAUNCHER.read_text(encoding="utf-8"), encoding="utf-8")
        r = subprocess.run([sys.executable, str(stand_in)],
                           capture_output=True, text=True, timeout=90)
        assert r.returncode == 0
        assert "not on this branch" in r.stderr

    def test_does_not_start_a_second_watcher(self):
        before = set(_live_watchers())
        if not before:
            pytest.skip("no watcher running; nothing to double")
        r = subprocess.run([sys.executable, str(LAUNCHER)],
                           capture_output=True, text=True, timeout=90)
        assert r.returncode == 0
        after = set(_live_watchers())
        assert after == before, f"launcher changed the watcher set: {before} -> {after}"
        assert len(after) <= 1, f"more than one watcher alive: {after}"


class TestOnlyOneWatcherOnThisMachine:
    def test_at_most_one_live_watcher(self):
        live = _live_watchers()
        assert len(live) <= 1, f"multiple watchers running: {live}"
