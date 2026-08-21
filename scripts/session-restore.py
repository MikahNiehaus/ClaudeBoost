"""
session-restore.py — Reopen the Claude Code sessions that were open before a reboot.

Reads state/session-restore.json (maintained by session-restore-ledger.py) and
opens one terminal tab per entry, each in its own directory, each running
`claude --resume <session-id>`.

Usage:
    python scripts/session-restore.py                 restore now (honours the boot guard)
    python scripts/session-restore.py --dry-run       print the exact commands, launch nothing
    python scripts/session-restore.py --status        show the ledger and what would happen
    python scripts/session-restore.py --seed          fill the ledger from what is open right now
    python scripts/session-restore.py --force         restore even if this boot was already done
    python scripts/session-restore.py --install-task  register the at logon scheduled task
    python scripts/session-restore.py --remove-task   remove it again
    python scripts/session-restore.py --from-task     what the scheduled task runs

Design notes worth knowing before editing this:

  Session id, not --continue. `claude --continue` resumes only the newest
  session in a directory, so two tabs open on the same directory would collapse
  into one. The ledger keeps real session ids, so each tab comes back as itself.

  A named Windows Terminal window, one call per tab. Chaining tabs with `;` in
  one command line means escaping the separator differently in PowerShell, cmd
  and a scheduled task action. A named window (-w <name>) makes every call
  independent and order does not matter.

  A launcher script per tab. Quoting a directory with spaces through wt.exe then
  cmd.exe then claude is the reliable way to get this wrong. ClaudeBoost already
  hit that in clear-safe-launch.py and solved it with a temp batch file.

  Nothing here is specific to one machine. Paths come from CLAUDEBOOST_HOME,
  Path.home() and PATH at run time, and the ledger records which machine wrote
  it so another machine's list is refused rather than reopened.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BOOST_HOME = Path(os.environ.get("CLAUDEBOOST_HOME") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BOOST_HOME / "scripts"))


class _LogStream:
    """Stand in for a missing stdout, appending to the restore log instead.

    The scheduled task runs under pythonw.exe, which has no console, so
    sys.stdout and sys.stderr are None. Any print, and even reading
    sys.stdout.isatty(), raises there. Left unhandled the script dies before it
    can log anything, so the login restore silently does nothing and the only
    evidence is a Last Result of 1 in Task Scheduler.

    Sending that output to the log instead means a login run is as traceable as
    a run from a terminal.
    """

    def __init__(self, path):
        self._path = path
        self._buf = ""

    def write(self, text):
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                try:
                    with open(self._path, "a", encoding="utf-8") as fh:
                        fh.write(f"  out: {line.rstrip()}\n")
                except Exception:
                    pass
        return len(text)

    def flush(self):
        if self._buf.strip():
            self.write("\n")

    def isatty(self):
        return False


def _ensure_streams() -> None:
    """Give the process real stdout and stderr before anything tries to print."""
    target = BOOST_HOME / "state" / "session-restore.log"
    try:
        (BOOST_HOME / "state").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    if sys.stdout is None:
        sys.stdout = _LogStream(target)
    if sys.stderr is None:
        sys.stderr = _LogStream(target)


_ensure_streams()

from session_restore_state import (  # noqa: E402
    boot_id,
    find_claude,
    find_terminal,
    ledger_path,
    live_sessions,
    log,
    machine_key,
    needs_call,
    now_iso,
    prune_stale,
    read_ledger,
    tabs_dir,
    update_ledger,
)

IS_WINDOWS = os.name == "nt"

TASK_NAME = "ClaudeBoost Session Restore"
WT_WINDOW = "claudeboost-restore"

# Seconds the scheduled task waits after logon before opening anything. Windows
# 11 can stall an interactive logon while mapped drives and VPN come up, and a
# tab that opens into a not yet mounted directory fails silently. The delay is
# the documented fix for that race.
LOGON_DELAY_SECONDS = 90

# getattr, not sys.stdout.isatty(), because a replaced or exotic stream may not
# implement isatty at all. Colour is cosmetic and must never be a failure point.
_USE_COLOR = bool(getattr(sys.stdout, "isatty", lambda: False)()) \
    and os.environ.get("TERM") != "dumb"
_C = {
    "cyan":   "\033[36m" if _USE_COLOR else "",
    "green":  "\033[32m" if _USE_COLOR else "",
    "yellow": "\033[33m" if _USE_COLOR else "",
    "red":    "\033[31m" if _USE_COLOR else "",
    "reset":  "\033[0m"  if _USE_COLOR else "",
}


def _say(msg: str, color: str = "") -> None:
    print(f"{_C.get(color, '')}{msg}{_C['reset']}")


def _ok(msg: str) -> None:   _say(f"[OK] {msg}", "green")
def _warn(msg: str) -> None: _say(f"[WARN] {msg}", "yellow")
def _err(msg: str) -> None:  _say(f"[ERROR] {msg}", "red")
def _skip(msg: str) -> None: _say(f"[SKIP] {msg}", "yellow")
def _info(msg: str) -> None: _say(msg, "cyan")


# ---------------------------------------------------------------------------
# Which entries to reopen
# ---------------------------------------------------------------------------
def _transcript_exists(cwd: str, session_id: str) -> bool | None:
    """Does the transcript for this session still exist on disk?

    Claude Code stores it at ~/.claude/projects/<mangled cwd>/<session id>.jsonl
    where the mangling replaces every non alphanumeric character with a dash.
    Very long paths are truncated and hashed instead, so a missing project
    directory is not proof of a missing session.

    Returns True (present), False (project dir exists but this session does
    not) or None (cannot tell). Only a hard False downgrades the tab to
    --continue, because guessing wrong loses the exact session the user wanted.
    """
    mangled = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    project_dir = Path.home() / ".claude" / "projects" / mangled
    if not project_dir.is_dir():
        return None
    return (project_dir / f"{session_id}.jsonl").is_file()


def _already_open(cwd: str) -> bool:
    """True if a Claude session is already live in this directory.

    Stops a manual restore run mid day from doubling every tab, and stops the
    scheduled task from piling on if it somehow fires twice.
    """
    target = str(Path(cwd)).rstrip("\\/").lower()
    for s in live_sessions():
        if str(Path(s["cwd"])).rstrip("\\/").lower() == target:
            return True
    return False


def _plan(force: bool = False) -> tuple[list[dict], list[str]]:
    """Return (entries to open, reasons things were skipped)."""
    data = read_ledger()
    notes: list[str] = []

    written_by = data.get("machine") or ""
    if written_by and written_by != machine_key():
        notes.append(f"ledger was written by {written_by}, this machine is {machine_key()}")
        return [], notes

    removed = prune_stale(data)
    if removed:
        notes.append(f"dropped {removed} stale entr{'y' if removed == 1 else 'ies'}")

    entries = list((data.get("sessions") or {}).values())
    entries.sort(key=lambda e: str(e.get("startedAt") or ""))

    keep: list[dict] = []
    for e in entries:
        cwd = str(e.get("cwd") or "")
        sid = str(e.get("sessionId") or "")
        if not cwd or not sid:
            notes.append("entry with no cwd or session id")
            continue
        if not Path(cwd).is_dir():
            notes.append(f"{e.get('name', sid[:8])}: directory gone ({cwd})")
            continue
        if not force and _already_open(cwd):
            notes.append(f"{e.get('name', sid[:8])}: already open in {cwd}")
            continue
        keep.append(e)
    return keep, notes


def _resume_args(entry: dict) -> list[str]:
    """The claude arguments for one tab."""
    sid = str(entry.get("sessionId") or "")
    cwd = str(entry.get("cwd") or "")
    flags = [str(f) for f in (entry.get("launchFlags") or [])]

    if _transcript_exists(cwd, sid) is False:
        # The project directory is there but this transcript is not, so the
        # session was cleaned up (cleanupPeriodDays, default 30). Fall back to
        # the newest session in that directory rather than failing to open.
        return ["--continue", *flags]
    return ["--resume", sid, *flags]


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------
def _write_tab_script(index: int, entry: dict, claude: str) -> Path:
    """One batch file per tab, so no quoting has to survive three layers."""
    cwd = str(Path(entry["cwd"]))
    name = str(entry.get("name") or Path(cwd).name)
    args = " ".join(_resume_args(entry))
    safe_title = name.replace("%", "").replace("&", " ").replace('"', "")

    # A .cmd or .bat shim invoked from a batch file without `call` transfers
    # control and never comes back, so the tab would end up in a broken state.
    invoke = "call " if needs_call(claude) else ""

    script = tabs_dir() / f"tab-{index:02d}.bat"
    script.write_text(
        "@echo off\r\n"
        f"title {safe_title}\r\n"
        f'cd /d "{cwd}"\r\n'
        f'{invoke}"{claude}" {args}\r\n',
        encoding="utf-8",
    )
    return script


def _launch(entry: dict, script: Path, kind: str, term: str, first: bool) -> bool:
    """Open one tab. Returns True if the launch was issued."""
    cwd = str(Path(entry["cwd"]))
    title = str(entry.get("name") or Path(cwd).name)
    comspec = os.environ.get("COMSPEC") or "cmd.exe"

    if kind == "wt":
        argv = [term, "-w", WT_WINDOW, "new-tab",
                "-d", cwd, "--title", title,
                comspec, "/k", str(script)]
    elif kind == "cmd":
        argv = [term, "/k", str(script)]
    else:
        return False

    flags = 0
    if IS_WINDOWS:
        # Detach so the launcher can exit without taking the tabs with it. The
        # same pair session-primer.py uses when it starts the RAG server.
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(argv, creationflags=flags, close_fds=True)
    except FileNotFoundError:
        return False
    except Exception as exc:
        log(f"launch failed for {title}: {exc}")
        return False

    if first:
        # Let the first call create and name the window before the next call
        # tries to attach a tab to it, otherwise a race opens two windows.
        time.sleep(1.2)
    else:
        time.sleep(0.25)
    return True


def seed(dry_run: bool) -> int:
    """Fill the ledger from the sessions open right now.

    The hooks only see sessions that start after they are installed, so a fresh
    install starts with an empty ledger and the first reboot restores nothing.
    This reads Claude Code's live registry once to close that gap. Also useful
    after deleting a ledger that went wrong.
    """
    live = live_sessions()
    if not live:
        _info("No live Claude sessions found, nothing to seed.")
        return 0

    if dry_run:
        _info(f"Would seed {len(live)} session(s):")
        for s in live:
            _say(f"  {s['name']:<28} {s['cwd']}")
        return 0

    def mutate(data: dict) -> None:
        sessions = data.setdefault("sessions", {})
        for s in live:
            existing = sessions.get(s["sessionId"], {})
            sessions[s["sessionId"]] = {
                "sessionId": s["sessionId"],
                "cwd": str(Path(s["cwd"])),
                "name": s["name"],
                "launchFlags": existing.get("launchFlags", []),
                "startedAt": existing.get("startedAt", now_iso()),
                "lastSeen": now_iso(),
                "lastSeenEpoch": time.time(),
                "seededFromLive": True,
            }

    update_ledger(mutate)
    _ok(f"seeded {len(live)} session(s) into {ledger_path()}")
    for s in live:
        _say(f"  {s['name']:<28} {s['cwd']}")
    log(f"seeded {len(live)} session(s) from the live registry")
    return 0


def restore(force: bool, dry_run: bool) -> int:
    entries, notes = _plan(force=force)

    for n in notes:
        _skip(n)

    if not entries:
        _info("Nothing to restore.")
        return 0

    current_boot = boot_id()
    if not force and not dry_run and current_boot:
        last = (read_ledger().get("lastRestore") or {}).get("bootId")
        if last and last == current_boot:
            _skip("this boot was already restored, use --force to run it again")
            log("skipped, boot already restored")
            return 0

    claude = find_claude()
    kind, term = find_terminal()

    if kind == "none":
        _warn("No Windows Terminal or console found. Open these by hand:")
        for e in entries:
            _say(f'  cd "{e["cwd"]}" && claude {" ".join(_resume_args(e))}')
        return 0

    if dry_run:
        _info(f"Would open {len(entries)} tab(s) via {kind} ({term}):\n")
        for i, e in enumerate(entries, 1):
            args = " ".join(_resume_args(e))
            _say(f"  {i}. {e.get('name', '?')}")
            _say(f"     dir  {e['cwd']}")
            _say(f"     run  \"{claude}\" {args}")
        _info(f"\nclaude resolved to: {claude}")
        _info(f"tab scripts would go in: {tabs_dir()}")
        return 0

    opened = 0
    for i, e in enumerate(entries, 1):
        script = _write_tab_script(i, e, claude)
        if _launch(e, script, kind, term, first=(opened == 0)):
            opened += 1
            _ok(f"{e.get('name', '?')}  ->  {e['cwd']}")
        else:
            _err(f"could not open {e.get('name', '?')}")

    def mark(data: dict) -> None:
        data["lastRestore"] = {
            "bootId": current_boot,
            "at": now_iso(),
            "opened": opened,
        }

    update_ledger(mark)
    log(f"restored {opened} of {len(entries)} session(s)")
    _info(f"\nOpened {opened} of {len(entries)} session(s).")
    return 0


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def status() -> int:
    data = read_ledger()
    sessions = data.get("sessions") or {}

    _info("=== ClaudeBoost Session Restore ===")
    print(f"ledger      {ledger_path()}")
    print(f"machine     {data.get('machine') or '(none)'}  (this machine: {machine_key()})")
    print(f"updated     {data.get('updatedAt') or '(never)'}")
    print(f"boot id     {boot_id() or '(unknown)'}")
    last = data.get("lastRestore") or {}
    print(f"last restore {last.get('at') or '(never)'}"
          f"{'  opened ' + str(last.get('opened')) if last.get('opened') is not None else ''}")
    print(f"claude      {find_claude()}")
    kind, term = find_terminal()
    print(f"terminal    {kind} {term}")
    print(f"task        {'registered' if _task_exists() else 'not registered'}")

    print(f"\nledger entries: {len(sessions)}")
    for e in sessions.values():
        live = "live" if _already_open(str(e.get("cwd") or "")) else "    "
        print(f"  [{live}] {str(e.get('name') or '?'):<28} {e.get('cwd')}")

    live = live_sessions()
    print(f"\nlive sessions right now: {len(live)}")
    for s in live:
        print(f"         {s['name']:<28} {s['cwd']}")

    entries, notes = _plan()
    print(f"\nwould reopen: {len(entries)}")
    for n in notes:
        print(f"  skip: {n}")
    return 0


# ---------------------------------------------------------------------------
# The at logon scheduled task
#
# ClaudeBoost has never registered anything at Windows login. Its own self
# healing runs from a hook inside an already open session, which cannot work
# here because the whole problem is that nothing is open yet. So this is the one
# OS level piece, and uninstall.py removes it in step with setup.py adding it.
# ---------------------------------------------------------------------------
def _pythonw() -> str:
    """Prefer pythonw.exe so the task does not flash a console window."""
    exe = Path(sys.executable)
    if IS_WINDOWS:
        candidate = exe.with_name("pythonw.exe")
        if candidate.is_file():
            return str(candidate)
    return str(exe)


def _task_xml() -> str:
    user = os.environ.get("USERNAME", "")
    domain = os.environ.get("USERDOMAIN", "")
    account = f"{domain}\\{user}" if domain and user else user
    command = _pythonw()
    script = BOOST_HOME / "scripts" / "session-restore.py"

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Reopens the Claude Code sessions that were open before the last shutdown. Installed by ClaudeBoost.</Description>
    <URI>\\{TASK_NAME}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>{account}</UserId>
      <Delay>PT{LOGON_DELAY_SECONDS}S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{account}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>"{script}" --from-task</Arguments>
      <WorkingDirectory>{BOOST_HOME}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _task_exists() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                           capture_output=True, text=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def _startup_shim_path() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return (Path(appdata) / "Microsoft" / "Windows" / "Start Menu"
            / "Programs" / "Startup" / "claudeboost-session-restore.cmd")


def install_task(dry_run: bool = False) -> int:
    """Register the at logon task. Falls back to a Startup folder shim if the
    machine's policy refuses task creation."""
    if not IS_WINDOWS:
        _skip("at logon task is Windows only, ledger and manual restore still work")
        return 0

    if dry_run:
        _info(f"would register scheduled task {TASK_NAME!r}:")
        print(_task_xml())
        return 0

    # schtasks /XML requires UTF-16, which is why this is not written as UTF-8.
    xml_path = tabs_dir().parent / "session-restore-task.xml"
    xml_path.write_text(_task_xml(), encoding="utf-16")

    try:
        r = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
            capture_output=True, text=True, timeout=60,
        )
    except Exception as exc:
        _err(f"schtasks could not run: {exc}")
        return 1

    if r.returncode == 0:
        _ok(f"scheduled task registered: {TASK_NAME} (at logon, {LOGON_DELAY_SECONDS}s delay)")
        xml_path.unlink(missing_ok=True)
        return 0

    _warn(f"schtasks refused the task: {(r.stderr or r.stdout).strip()}")
    _info("Falling back to a Startup folder shim, which needs no privileges.")

    shim = _startup_shim_path()
    try:
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.write_text(
            "@echo off\r\n"
            "rem Installed by ClaudeBoost session restore. Safe to delete.\r\n"
            f"timeout /t {LOGON_DELAY_SECONDS} /nobreak >nul\r\n"
            f'"{_pythonw()}" "{BOOST_HOME / "scripts" / "session-restore.py"}" --from-task\r\n',
            encoding="utf-8",
        )
        _ok(f"startup shim written: {shim}")
        return 0
    except Exception as exc:
        _err(f"startup shim failed too: {exc}")
        _info("Register it by hand, or run /restore-sessions after each reboot.")
        return 1


def remove_task(dry_run: bool = False) -> int:
    """Remove both the task and the Startup shim. Called by uninstall.py."""
    if not IS_WINDOWS:
        return 0

    removed = False

    if _task_exists():
        if dry_run:
            _info(f"would delete scheduled task {TASK_NAME!r}")
            removed = True
        else:
            try:
                r = subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                                   capture_output=True, text=True, timeout=60)
                if r.returncode == 0:
                    _ok(f"scheduled task removed: {TASK_NAME}")
                    removed = True
                else:
                    _warn(f"could not remove the task: {(r.stderr or r.stdout).strip()}")
            except Exception as exc:
                _warn(f"schtasks delete failed: {exc}")
    else:
        _skip(f"scheduled task {TASK_NAME!r} is not registered")

    shim = _startup_shim_path()
    if shim.exists():
        if dry_run:
            _info(f"would delete startup shim {shim}")
        else:
            try:
                shim.unlink()
                _ok(f"startup shim removed: {shim}")
                removed = True
            except Exception as exc:
                _warn(f"could not remove the startup shim: {exc}")

    return 0 if removed or not _task_exists() else 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser(
        description="Reopen the Claude Code sessions that were open before a reboot.")
    p.add_argument("--dry-run", action="store_true", help="print the commands, launch nothing")
    p.add_argument("--status", action="store_true", help="show the ledger and what would happen")
    p.add_argument("--force", action="store_true", help="restore even if this boot was already done")
    p.add_argument("--install-task", action="store_true", help="register the at logon task")
    p.add_argument("--remove-task", action="store_true", help="remove the at logon task")
    p.add_argument("--from-task", action="store_true", help="marks a run by the scheduled task")
    p.add_argument("--seed", action="store_true",
                   help="fill the ledger from the sessions open right now")
    args = p.parse_args()

    if args.status:
        return status()
    if args.seed:
        return seed(dry_run=args.dry_run)
    if args.install_task:
        return install_task(dry_run=args.dry_run)
    if args.remove_task:
        return remove_task(dry_run=args.dry_run)

    if args.from_task:
        log("scheduled task fired")

    return restore(force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
