"""Record how every claude.exe process ends, with its real exit code.

Why this exists
---------------
Claude Code sessions on this machine keep disappearing and nothing records why.
Everything cheap has already been ruled out:

  - Memory. scripts/memory-watcher.py caught four disappearances on 2026-08-26
    at 10.5 GB, 7.6 GB, 3.6 GB and 12.1 GB free, on a 33.8 GB machine. A process
    dying with 12 GB free is not dying of memory.
  - A crash. No Windows Error Reporting report, no Application log 1000/1001,
    no System log 6008, no Resource-Exhaustion-Detector 2004.
  - scripts/auto-clear.py, the one hook in the tree that calls os.kill(pid, 9)
    on its own editor. Its audit log was added first and stayed empty across a
    later disappearance, so it never fired.

The remaining question is one bit wide: did the process exit on its own, or did
something terminate it. An exit code answers that and nothing else here does.

  0            clean exit
  1            the usual code when TerminateProcess is called with 1
  9            os.kill(pid, 9) on Windows, which is TerminateProcess(9)
  0xC0000005   access violation, a real crash
  0xC0000409   stack buffer overrun
  other large 0xC0000xxx values are NTSTATUS crash codes

Why polling and handles rather than an event log
------------------------------------------------
Win32_ProcessStopTrace and Security log 4689 both need administrator rights or
an audit policy change. This needs neither. A handle opened with
PROCESS_QUERY_LIMITED_INFORMATION keeps the exit code readable after the process
is gone, which is the whole trick: without a held handle the PID is recycled and
the code is unrecoverable.

Run it detached and leave it running:

    python scripts/claude-exit-watcher.py

Appends one JSON object per exit to state/claude-exits.jsonl, flushed and
fsynced per line because the thing being investigated takes the machine down.
"""

import ctypes
import ctypes.wintypes
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

if sys.platform != "win32":
    print("Windows only.", file=sys.stderr)
    raise SystemExit(1)

try:
    import psutil
except ImportError:
    print("psutil is required: pip install psutil", file=sys.stderr)
    raise SystemExit(1)

#: Names worth watching. claude.exe is the editor; node.exe is what it runs as
#: on some installs, which is exactly why auto-clear.py's ancestor walk accepts
#: either.
WATCH_NAMES = {"claude.exe", "node.exe"}

POLL_S = 1.0
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000

OUT = Path(__file__).resolve().parents[1] / "state" / "claude-exits.jsonl"

#: Claude Code's auto updater writes its result here. Captured at exit time
#: because it is the leading suspect and it is destructive evidence: the file
#: holds only the LAST result, so reading it minutes later can show a different
#: update than the one that coincided with the exit.
#:
#: On 2026-08-26 a session ended with exit code 9 at 21:00:43Z and an update
#: from 2.1.245 to 2.1.246 recorded success at 21:04:21Z, four minutes later.
#: Correlating those by hand needed both timestamps to still exist. The next
#: one should not need that luck.
UPDATE_RESULT = Path.home() / ".claude" / ".last-update-result.json"

kernel32 = ctypes.windll.kernel32


def _update_state() -> dict:
    """What the auto updater last reported, plus how fresh that report is.

    Returns a dict with an "error" key rather than raising. A watcher that dies
    while recording a crash records nothing, which defeats the point.
    """
    try:
        raw = UPDATE_RESULT.read_text(encoding="utf-8")
        data = json.loads(raw)
        age = time.time() - UPDATE_RESULT.stat().st_mtime
        return {"age_s": round(age, 1), "result": data}
    except FileNotFoundError:
        return {"age_s": None, "result": None}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _updater_running(alive_cmdlines: list[str]) -> list[str]:
    """Any npm or update processes in flight at this instant.

    An update that is mid flight has not written its result file yet, so the
    result file alone would say "nothing happened" during exactly the window
    that matters most.
    """
    needles = ("npm-cli.js", "npx-cli.js", "npm view", "claude-code@latest", "npm install")
    return [c[:200] for c in alive_cmdlines if any(n in c for n in needles)]


def _open(pid: int):
    """Handle that keeps the exit code readable after the process is gone.

    Returns None when the process is already gone or is not ours to open. Both
    are ordinary, not errors: the watcher sees processes it has no rights to.
    """
    return kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid
    ) or None


def _exit_code(handle):
    """The process's exit code, or None while it is still running."""
    code = ctypes.wintypes.DWORD()
    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
        return None
    return None if code.value == STILL_ACTIVE else code.value


def _describe(code: int) -> str:
    known = {
        0: "clean exit",
        1: "terminated (TerminateProcess with 1), or exited with status 1",
        9: "terminated with 9 (what os.kill(pid, 9) does on Windows)",
        0xC0000005: "ACCESS_VIOLATION (real crash)",
        0xC0000409: "STACK_BUFFER_OVERRUN (real crash)",
        0xC000013A: "CONTROL_C_EXIT (console Ctrl+C / Ctrl+Break)",
        0xC0000374: "HEAP_CORRUPTION (real crash)",
    }
    if code in known:
        return known[code]
    if code >= 0xC0000000:
        return f"NTSTATUS 0x{code:08X} (crash)"
    return f"exit status {code}"


def _write(record: dict) -> None:
    """Append one line, flushed and fsynced.

    Buffering would lose exactly the record that matters if the machine goes
    down, which is the scenario being investigated.
    """
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def main() -> int:
    # pid -> (handle, name, cmdline, first_seen_iso)
    tracked: dict[int, tuple] = {}

    print(f"Watching {', '.join(sorted(WATCH_NAMES))}. Writing {OUT}")
    print("Leave this running. Ctrl+C to stop.")

    while True:
        alive = set()
        alive_cmdlines: list[str] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info["name"] or "").lower()
                # Collected across ALL processes, not just watched ones: the
                # updater runs as npm/npx, which is neither claude.exe nor a
                # process this loop would otherwise look at.
                if name.startswith(("npm", "npx", "node", "cmd")):
                    joined = " ".join(proc.info["cmdline"] or "")
                    if joined:
                        alive_cmdlines.append(joined)
                if name not in WATCH_NAMES:
                    continue
                pid = proc.info["pid"]
                alive.add(pid)
                if pid in tracked:
                    continue
                handle = _open(pid)
                if handle is None:
                    continue
                cmdline = " ".join(proc.info["cmdline"] or [])[:400]
                tracked[pid] = (
                    handle,
                    name,
                    cmdline,
                    datetime.now(timezone.utc).isoformat(),
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        for pid in list(tracked):
            handle, name, cmdline, first_seen = tracked[pid]
            code = _exit_code(handle)
            if code is None:
                continue
            _write({
                "t": datetime.now(timezone.utc).isoformat(),
                "pid": pid,
                "name": name,
                "exit_code": code,
                "exit_code_hex": f"0x{code:08X}",
                "meaning": _describe(code),
                "first_seen": first_seen,
                "cmdline": cmdline,
                "other_watched_alive": sorted(alive - {pid}),
                # The correlation, captured now rather than reconstructed later.
                "last_update_result": _update_state(),
                "updater_processes_now": _updater_running(alive_cmdlines),
            })
            print(f"{name} pid={pid} exited: {_describe(code)}")
            kernel32.CloseHandle(handle)
            del tracked[pid]

        time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
