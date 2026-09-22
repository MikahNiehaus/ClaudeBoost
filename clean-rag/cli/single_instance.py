"""One console per clean-rag home, enforced by a Windows named mutex.

The problem this solves: `server_ctl.py start` calls `_launch_console()` on
both its paths, including the one where the server is already running, so
running `start` twice opened two console windows and running it ten times
opened ten.

Why a named mutex rather than a PID file or a lock file. A mutex is a kernel
object, so Windows releases it when the owning process ends for any reason at
all: a clean exit, the user clicking the X on the window, Task Manager, a
crash. There is no stale state to detect and no cleanup code that has to run.
A marker file has the opposite property, because closing a window runs no
cleanup, so the marker outlives the process and the next launch wrongly decides
a console is already up. `tendo.singleton` shows where that road ends: it
deletes any pre-existing lock file before creating its own, which defeats the
guard it is trying to be.

Why the guard lives here and not in `server_ctl.py`. The launcher exits in
under a second, so a mutex it held would release immediately and guard
nothing. The mutex has to be held by the long lived process, which is the
console.

Shape of the ctypes wrapper taken from benhoyt/namedmutex (BSD 3 clause),
with one correction. That reference tests `if not ret` for the already running
case, and that test never fires: `CreateMutexW` returns a valid handle whether
or not the mutex existed. Microsoft's documentation is explicit that the only
signal is `GetLastError`, which is why `use_last_error=True` and the
`ERROR_ALREADY_EXISTS` check below are load bearing.

Every failure here answers "no console is running", so a guard that cannot
tell lets the console open. A wrong "yes" would leave someone with no way to
open the console at all, which is worse than a second window.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

#: Windows sets this when CreateMutexW opened an existing mutex instead of
#: making a new one. From winerror.h, and the only way to tell the two apart.
ERROR_ALREADY_EXISTS = 183

#: The live mutex handle, kept for the life of the process. Windows frees it on
#: exit, so nothing closes it here. It is a module global because a local would
#: say nothing about the lifetime the mutex actually needs.
_held_handle: int | None = None


def mutex_name(home: Path | str) -> str:
    """The mutex name for one clean-rag checkout.

    Two checkouts on one machine each get their own console, so the name
    carries a hash of the home path. sha256 truncated to 12 is the same shape
    `state/projects.json` already uses for project keys.

    The `Local\\` namespace is per logon session. `Global\\` would let one
    signed in user's console block another's, and its creation can be refused
    outright without the right privilege, which would make the guard fail open
    for a reason that has nothing to do with whether a console is running.
    """
    digest = hashlib.sha256(str(Path(home).resolve()).encode("utf-8")).hexdigest()[:12]
    return f"Local\\CleanRagConsole_{digest}"


def already_running(home: Path | str) -> bool:
    """Is a console already up for *home*?

    Returns False on any platform that is not Windows and on any failure,
    because the console opening twice is recoverable and the console never
    opening is not.
    """
    global _held_handle

    if sys.platform != "win32":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateMutexW(None, False, mutex_name(home))
        if not handle:
            return False

        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            # Someone else owns it, so drop this handle rather than leaving a
            # reference to a mutex this process is about to stop caring about.
            kernel32.CloseHandle(handle)
            return True

        _held_handle = handle
        return False
    except Exception:
        return False
