"""
session_restore_state.py — Shared state for ClaudeBoost session restore.

The problem this solves: a reboot kills every open Claude Code session, and
Claude Code has no reopen everything feature. Only `--continue` (newest session
in one directory) and `--resume <id>` (one named session) exist, both manual.

The ledger is the answer. `session-restore-ledger.py` records a session on
SessionStart and removes it on SessionEnd, so whatever is still listed is what
was open when the machine went down. `session-restore.py` reads it at login and
reopens one terminal tab per entry.

Why a ledger and not a snapshot at shutdown: Windows gives shutdown hooks no
guarantee they finish, so an unclean reboot is exactly when a shutdown time
snapshot would lose the data. The hooks are event driven instead, and a reboot
that skips SessionEnd leaves the entry behind, which is the outcome we want.

Claude Code also keeps a live registry at ~/.claude/sessions/<pid>.json carrying
pid, sessionId, cwd, name and procStart. That is internal plumbing and the docs
warn its format can change on any release, so it is read only as a cross check
and every read is defensive. The hook payload is the documented source.

Everything here is machine local. The ledger records platform.node() and restore
ignores entries from a different machine, so a state directory that ever travels
between computers cannot reopen paths that do not exist here.

Public API:
    state_dir()                  -> Path
    ledger_path()                -> Path
    read_ledger()                -> dict
    update_ledger(mutator)       -> dict        (locked read then write)
    machine_key()                -> str
    boot_id()                    -> str
    pid_alive(pid)               -> bool
    live_sessions()              -> list[dict]
    find_claude()                -> str
    find_terminal()              -> tuple[str, str]
    log(message)                 -> None
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)

LEDGER_SCHEMA = 1

# An entry nobody has touched in this long is assumed abandoned rather than
# open. Without it a session that died to a crash (no SessionEnd) would be
# reopened at every login forever.
STALE_AFTER_DAYS = 14

_LOCK_TIMEOUT_S = 2.0
_LOCK_STALE_S = 5.0


# ---------------------------------------------------------------------------
# Paths. Everything lands under state/, which .gitignore excludes wholesale,
# because a list of this machine's open windows is not portable and must never
# be committed.
# ---------------------------------------------------------------------------
def state_dir() -> Path:
    d = BOOST_HOME / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ledger_path() -> Path:
    return state_dir() / "session-restore.json"


def log_path() -> Path:
    return state_dir() / "session-restore.log"


def tabs_dir() -> Path:
    """Per tab launcher scripts written at restore time.

    Each tab gets its own tiny script rather than a quoted inline command.
    Nesting quotes through wt.exe then cmd.exe then claude is the documented
    way to get this wrong, and ClaudeBoost already learned that lesson in
    clear-safe-launch.py ("dodge cmd.exe quoting hell with nested quotes").
    """
    d = state_dir() / "session-restore-tabs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(message: str) -> None:
    """Append one line to the restore log. Never raises, never blocks a hook."""
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with log_path().open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp}  {message}\n")
    except Exception:
        pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Machine and boot identity
# ---------------------------------------------------------------------------
def machine_key() -> str:
    """Stable per machine name, used to refuse another machine's ledger."""
    return platform.node() or "unknown"


def boot_id() -> str:
    """Approximate boot timestamp, as a coarse string.

    Restore compares this against the boot it last ran for, so logging out and
    back in does not reopen every tab a second time. Rounded to 60 seconds
    because uptime clocks drift a little between reads, and an exact match is
    not needed to tell one boot from another.
    """
    uptime_s: float | None = None
    try:
        if os.name == "nt":
            import ctypes
            uptime_s = ctypes.windll.kernel32.GetTickCount64() / 1000.0
        elif sys.platform.startswith("linux"):
            uptime_s = float(Path("/proc/uptime").read_text().split()[0])
        elif sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["sysctl", "-n", "kern.boottime"],
                                 capture_output=True, text=True, timeout=5).stdout
            sec = out.split("sec = ")[1].split(",")[0].strip()
            return f"boot-{int(float(sec)) // 60}"
    except Exception:
        uptime_s = None

    if uptime_s is None:
        return ""
    return f"boot-{int((time.time() - uptime_s) // 60)}"


# ---------------------------------------------------------------------------
# Ledger read and write. Concurrent SessionStart hooks from several sessions
# opening at once would otherwise lose entries to a read then write race, so
# writes go through an advisory lock, the same pattern telemetry_writer.py uses.
# ---------------------------------------------------------------------------
def _empty_ledger() -> dict:
    return {
        "schema": LEDGER_SCHEMA,
        "machine": machine_key(),
        "updatedAt": now_iso(),
        "sessions": {},
        "lastRestore": {},
    }


def read_ledger() -> dict:
    try:
        data = json.loads(ledger_path().read_text(encoding="utf-8-sig"))
    except Exception:
        return _empty_ledger()
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
        return _empty_ledger()
    data.setdefault("schema", LEDGER_SCHEMA)
    data.setdefault("machine", machine_key())
    data.setdefault("lastRestore", {})
    return data


def _acquire_lock(lock_path: Path) -> bool:
    deadline = time.monotonic() + _LOCK_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            lock_path.open("x").close()  # O_EXCL, fails if the lock is held
            return True
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _LOCK_STALE_S:
                    lock_path.unlink(missing_ok=True)
                    continue  # a crashed writer left it behind
            except Exception:
                pass
            time.sleep(0.02)
        except Exception:
            return False
    return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass


def _write_ledger(data: dict) -> None:
    """Write via a temp file and replace, so a crash mid write cannot leave a
    truncated ledger. A half written ledger reads as no sessions, which would
    silently lose the whole restore list."""
    data["updatedAt"] = now_iso()
    data["machine"] = machine_key()
    path = ledger_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def update_ledger(mutator: Callable[[dict], None]) -> dict:
    """Locked read then write. `mutator` edits the dict in place.

    Returns the written ledger. If the lock cannot be taken the mutation is
    skipped rather than applied unsafely, and the miss is logged. Losing one
    ledger update is recoverable: the next SessionStart or the live registry
    cross check picks the session back up.
    """
    lock = ledger_path().with_suffix(".json.lock")
    if not _acquire_lock(lock):
        log("ledger lock busy, skipped an update")
        return read_ledger()
    try:
        data = read_ledger()
        mutator(data)
        prune_stale(data)
        _write_ledger(data)
        return data
    except Exception as exc:
        log(f"ledger update failed: {exc}")
        return read_ledger()
    finally:
        _release_lock(lock)


def prune_stale(data: dict) -> int:
    """Drop entries whose directory is gone or that nobody has touched in
    STALE_AFTER_DAYS. Returns how many were removed."""
    sessions = data.get("sessions") or {}
    cutoff = time.time() - (STALE_AFTER_DAYS * 86400)
    doomed = []
    for sid, entry in sessions.items():
        cwd = entry.get("cwd") or ""
        if not cwd or not Path(cwd).is_dir():
            doomed.append(sid)
            continue
        seen = entry.get("lastSeenEpoch")
        if isinstance(seen, (int, float)) and seen < cutoff:
            doomed.append(sid)
    for sid in doomed:
        sessions.pop(sid, None)
    return len(doomed)


# ---------------------------------------------------------------------------
# Live process checks
# ---------------------------------------------------------------------------
def pid_alive(pid: int) -> bool:
    """True if that pid is currently running.

    os.kill(pid, 0) is the POSIX idiom but is unreliable on Windows, so
    Windows goes through OpenProcess and checks the exit code, which
    distinguishes "running" from "exited but still has a handle open".
    """
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            k32 = ctypes.windll.kernel32
            handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
                return False
            finally:
                k32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        # PermissionError means it exists but belongs to somebody else.
        return isinstance(sys.exc_info()[1], PermissionError)
    except Exception:
        return False


def proc_start_filetime(pid: int) -> int | None:
    """Windows FILETIME the process started, or None if it cannot be read.

    This is what pins a pid to one specific process. Windows reuses pids
    freely, and after a reboot it reassigns them from scratch, so "that pid is
    alive" says nothing about whether it is still the process that recorded it.
    """
    if os.name != "nt" or not pid or pid <= 0:
        return None
    try:
        import ctypes
        import ctypes.wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return None
        try:
            created = ctypes.wintypes.FILETIME()
            exited = ctypes.wintypes.FILETIME()
            kernel = ctypes.wintypes.FILETIME()
            user = ctypes.wintypes.FILETIME()
            ok = k32.GetProcessTimes(handle,
                                     ctypes.byref(created), ctypes.byref(exited),
                                     ctypes.byref(kernel), ctypes.byref(user))
            if not ok:
                return None
            return (created.dwHighDateTime << 32) | created.dwLowDateTime
        finally:
            k32.CloseHandle(handle)
    except Exception:
        return None


def _same_process(pid: int, recorded_start: str | int | None) -> bool:
    """Is pid still the process that wrote recorded_start?

    Returns True when it cannot tell, because a pid that is alive and
    unverifiable is more likely the real session than a recycled one, and a
    wrong "dead" here only costs a duplicate tab while a wrong "live" silently
    drops a session from the restore.

    A recycled pid is caught because its creation time differs. Tolerance is
    two seconds in FILETIME units, absorbing rounding between what Claude Code
    recorded and what the kernel reports.
    """
    if recorded_start in (None, ""):
        return True
    actual = proc_start_filetime(pid)
    if actual is None:
        return True
    try:
        recorded = int(str(recorded_start))
    except Exception:
        return True
    return abs(actual - recorded) <= 20_000_000


def live_sessions() -> list[dict]:
    """Read Claude Code's own live session registry, best effort.

    ~/.claude/sessions/<pid>.json is internal and undocumented. Every field is
    optional here and any parse failure is skipped silently, because this is
    only a cross check: the hook payload is the real source. If a future
    Claude Code release changes or drops these files, restore keeps working off
    the ledger alone.
    """
    out: list[dict] = []
    d = Path.home() / ".claude" / "sessions"
    if not d.is_dir():
        return out
    try:
        files = list(d.glob("*.json"))
    except Exception:
        return out
    for f in files:
        try:
            s = json.loads(f.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(s, dict):
            continue
        sid = s.get("sessionId")
        cwd = s.get("cwd")
        if not sid or not cwd:
            continue
        if s.get("kind") and s.get("kind") != "interactive":
            continue  # a -p run or SDK session has no terminal to reopen
        try:
            pid = int(s.get("pid") or 0)
        except Exception:
            pid = 0
        if pid and not pid_alive(pid):
            continue
        # A live pid is not enough. After a reboot these files can linger with
        # pids Windows has since handed to unrelated processes, and treating one
        # of those as a live session would make restore skip that directory.
        if pid and not _same_process(pid, s.get("procStart")):
            continue
        out.append({
            "sessionId": str(sid),
            "cwd": str(cwd),
            "name": str(s.get("name") or Path(str(cwd)).name),
            "pid": pid,
            "version": str(s.get("version") or ""),
        })
    return out


# ---------------------------------------------------------------------------
# Executable discovery. Nothing here is hardcoded to one machine: every path
# comes from PATH or a home relative lookup at run time.
# ---------------------------------------------------------------------------
def _claude_candidates() -> list[Path]:
    """Known install locations, for when PATH is not enough.

    A task launched at logon does not always inherit the PATH an interactive
    shell has, so PATH alone cannot be relied on to find the CLI.
    """
    out: list[Path] = []
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            out.append(Path(appdata) / "npm" / "node_modules"
                       / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe")
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            out.append(Path(local) / "Programs" / "claude" / "claude.exe")
        out.append(Path.home() / ".local" / "bin" / "claude.exe")
    else:
        out.append(Path.home() / ".local" / "bin" / "claude")
        out.append(Path("/usr/local/bin/claude"))
    return out


def find_claude() -> str:
    """Absolute path to the claude CLI, preferring a real executable.

    On Windows shutil.which("claude") usually returns npm's claude.CMD shim,
    because PATHEXT lists .CMD ahead of nothing else matching. The shim works,
    but a real .exe skips an extra batch layer inside the tab launcher, so a
    matching .exe wins when one exists. When only the shim is found, the
    launcher invokes it with `call`, which is what one batch file needs to run
    another and still get control back.
    """
    for c in _claude_candidates():
        try:
            if c.is_file():
                return str(c)
        except Exception:
            pass

    found = shutil.which("claude")
    if found:
        return found

    return "claude"


def needs_call(exe: str) -> bool:
    """True if this path is a batch shim, which a .bat must invoke with `call`."""
    return str(exe).lower().endswith((".cmd", ".bat"))


def find_terminal() -> tuple[str, str]:
    """Return (kind, path) for the terminal to open tabs in.

    kind is "wt" for Windows Terminal, "cmd" for a plain console window, or
    "none" when neither applies (macOS and Linux, where restore prints the
    commands instead of guessing at a terminal emulator).
    """
    if os.name != "nt":
        return ("none", "")
    wt = shutil.which("wt.exe") or shutil.which("wt")
    if wt:
        return ("wt", wt)
    cmd = shutil.which("cmd.exe") or os.environ.get("COMSPEC", "")
    if cmd:
        return ("cmd", cmd)
    return ("none", "")
