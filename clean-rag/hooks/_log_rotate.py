"""Keep a hook's log file from growing without limit.

Why this is not logging.handlers.RotatingFileHandler. That class rotates from
inside the writing process, and every hook here is a SEPARATE short lived
process, one per tool call. Two of them crossing the size threshold at the same
moment both try to rename the same file, and on Windows a rename fails outright
while another process holds the file open. The result is PermissionError
(WinError 32) raised on every emit, spraying the failure into stderr, which for a
PreToolUse hook is worse than the oversized log it was meant to fix.

The maintained fix for genuinely concurrent rotation is concurrent-log-handler,
which takes a real cross process lock. It is not used here because it is a new
runtime dependency for the sake of a log file, and because these processes do not
need to coordinate: each one runs for a few milliseconds, so the check below
happens BEFORE the log is opened for the run rather than during it, and a
collision costs one skipped rotation rather than a raised exception.

Best effort throughout, on purpose. A hook that cannot rotate its log must still
do its actual job.
"""
from __future__ import annotations

import os
from pathlib import Path

#: 5 MB, matching the cap already used for server.log in server/app.py.
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


def trim_if_large(path: str | os.PathLike, max_bytes: int = DEFAULT_MAX_BYTES) -> bool:
    """Move *path* aside when it has grown past *max_bytes*.

    One generation is kept, at ``<name>.1``, which is enough to still have the
    recent history after a rotation without keeping an unbounded set of files.

    Returns True when a rotation happened. Callers do not have to check; the
    return value exists so a test can tell "rotated" from "left alone", which is
    otherwise only visible as a side effect on disk.

    Never raises. Every failure mode here (another process holding the handle,
    a read only directory, the file vanishing between the size check and the
    rename) ends with the log simply not rotated this time, and the next hook
    invocation gets another attempt.
    """
    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False

    previous = p.with_name(p.name + ".1")
    try:
        # Windows will not replace an existing target, so clear it first. POSIX
        # would overwrite silently, but doing it explicitly keeps both platforms
        # on the same path.
        if previous.exists():
            previous.unlink()
        p.rename(previous)
        return True
    except OSError:
        # Almost always another hook process holding the file open. Leave it,
        # the next invocation over the threshold will try again.
        return False
