"""The exit watcher must tell a clean exit apart from a kill.

That distinction is the entire reason the script exists. Claude Code sessions
were disappearing on 2026-08-26 with no Windows Error Reporting entry, no
Application log crash event, and enough free RAM to rule out memory, so the one
remaining question was whether the process chose to exit or was terminated. If
_exit_code cannot read a real code off a real dead process, the script answers
nothing and would have been trusted anyway.

So these tests spawn real processes, end them two different ways, and read the
codes back.
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows only: uses OpenProcess/GetExitCodeProcess"
)


def _load():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "claude-exit-watcher.py"
    spec = importlib.util.spec_from_file_location("claude_exit_watcher", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wait_for_code(mod, handle, timeout_s=15.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        code = mod._exit_code(handle)
        if code is not None:
            return code
        time.sleep(0.05)
    return None


def test_reads_a_clean_exit_code():
    """A process that exits on its own reports its own status."""
    mod = _load()
    proc = subprocess.Popen([sys.executable, "-c", "raise SystemExit(42)"])
    handle = mod._open(proc.pid)
    assert handle is not None, "could not open a process this test just spawned"
    try:
        proc.wait(timeout=15)
        assert _wait_for_code(mod, handle) == 42
    finally:
        mod.kernel32.CloseHandle(handle)


def test_reads_a_termination_code():
    """A killed process reports the kill code, not 0.

    This is the case the investigation turns on. If a terminated process came
    back as 0 the watcher would report every kill as a clean exit.
    """
    mod = _load()
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    handle = mod._open(proc.pid)
    assert handle is not None
    try:
        time.sleep(0.3)  # let it get past interpreter startup
        proc.kill()      # TerminateProcess on Windows
        proc.wait(timeout=15)
        code = _wait_for_code(mod, handle)
        assert code is not None
        assert code != 0, "a killed process must not report a clean exit"
    finally:
        mod.kernel32.CloseHandle(handle)


def test_a_running_process_reports_no_code_yet():
    """Still running must read as None, not as 259 leaking through."""
    mod = _load()
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    handle = mod._open(proc.pid)
    assert handle is not None
    try:
        time.sleep(0.3)
        assert mod._exit_code(handle) is None
    finally:
        proc.kill()
        proc.wait(timeout=15)
        mod.kernel32.CloseHandle(handle)


def test_the_handle_outlives_the_process():
    """The code stays readable after the process is gone.

    Without a held handle the PID is recycled and the exit code is
    unrecoverable, so this is the property that makes the whole approach work
    rather than an implementation detail.
    """
    mod = _load()
    proc = subprocess.Popen([sys.executable, "-c", "raise SystemExit(7)"])
    handle = mod._open(proc.pid)
    assert handle is not None
    try:
        proc.wait(timeout=15)
        time.sleep(1.0)  # well after the process is gone
        assert _wait_for_code(mod, handle) == 7
    finally:
        mod.kernel32.CloseHandle(handle)


@pytest.mark.parametrize("code,expected", [
    (0, "clean exit"),
    (9, "terminated"),
    (0xC0000005, "ACCESS_VIOLATION"),
])
def test_describe_names_the_important_codes(code, expected):
    mod = _load()
    assert expected in mod._describe(code)


def test_describe_flags_unknown_ntstatus_as_a_crash():
    mod = _load()
    assert "crash" in mod._describe(0xC0000123)


def test_update_state_reads_the_result_and_its_age(tmp_path, monkeypatch):
    """The updater correlation must survive being read at exit time.

    The result file holds only the LAST update, so it is destructive evidence.
    Reading it minutes later can show a different update than the one that
    coincided with the exit, which is why age_s is recorded alongside it.
    """
    import json
    mod = _load()
    f = tmp_path / ".last-update-result.json"
    payload = {"outcome": "success", "version_from": "2.1.245", "version_to": "2.1.246"}
    f.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(mod, "UPDATE_RESULT", f)

    state = mod._update_state()
    assert state["result"] == payload
    assert state["age_s"] is not None and state["age_s"] >= 0


def test_update_state_survives_a_missing_or_corrupt_file(tmp_path, monkeypatch):
    """A watcher that raises while recording a crash records nothing."""
    mod = _load()
    missing = tmp_path / "nope.json"
    monkeypatch.setattr(mod, "UPDATE_RESULT", missing)
    assert mod._update_state() == {"age_s": None, "result": None}

    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(mod, "UPDATE_RESULT", corrupt)
    assert "error" in mod._update_state()


def test_updater_processes_are_recognised():
    """An update in flight has not written its result file yet.

    Without this, the record would say "no update happened" during exactly the
    window where one was running.
    """
    mod = _load()
    cmdlines = [
        r"C:\Program Files\nodejs\node.exe C:\...\npm\bin\npm-cli.js view @anthropic-ai/claude-code@latest version",
        r"C:\Program Files\nodejs\node.exe C:\...\npm\bin\npx-cli.js -y @playwright/mcp@latest",
        r"C:\Users\x\claude.exe --continue",
    ]
    found = mod._updater_running(cmdlines)
    assert any("npm-cli.js" in f for f in found)
    assert not any("claude.exe --continue" in f for f in found), (
        "the editor itself is not an updater process"
    )


def test_the_record_is_actually_written_and_readable(tmp_path, monkeypatch):
    """A silent write failure would waste the next crash, which is the point.

    The watcher runs for hours to capture one event. If _write fails quietly,
    that event is gone and there is no second chance at it, so the write path
    gets its own test rather than being assumed.
    """
    mod = _load()
    out = tmp_path / "state" / "claude-exits.jsonl"
    monkeypatch.setattr(mod, "OUT", out)

    mod._write({"t": "2026-08-26T21:00:00+00:00", "pid": 123, "exit_code": 9})
    mod._write({"t": "2026-08-26T21:00:05+00:00", "pid": 456, "exit_code": 0})

    lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2, "appending must not overwrite the previous record"
    import json
    assert json.loads(lines[0])["exit_code"] == 9
    assert json.loads(lines[1])["pid"] == 456


def test_the_watcher_opens_handles_for_the_names_it_watches(monkeypatch):
    """The names in WATCH_NAMES must match what psutil actually reports.

    psutil returns the executable name, and the comparison is lowercased on
    both sides. A mismatch here would leave the watcher running for hours
    watching nothing, and it would look identical to "no crashes happened".
    """
    mod = _load()
    assert mod.WATCH_NAMES == {n.lower() for n in mod.WATCH_NAMES}, (
        "WATCH_NAMES must be lowercase; the lookup lowercases the process name"
    )

    import psutil
    seen = set()
    for proc in psutil.process_iter(["name"]):
        try:
            seen.add((proc.info["name"] or "").lower())
        except psutil.Error:
            continue
    assert seen & mod.WATCH_NAMES, (
        f"none of {mod.WATCH_NAMES} are running, so the watcher would record "
        f"nothing. Running process names sampled: {sorted(seen)[:20]}"
    )
