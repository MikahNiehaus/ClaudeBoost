"""Tail a log file that rotates underneath you, without blocking the rotation.

Textualize/toolong's PollWatcher keeps one fd open forever and lseeks along it.
That is fine for the fixed files toolong is handed on the command line, and it
is wrong here for two separate reasons.

It misses rotation. clean-rag's log is a RotatingFileHandler at 5 MB with 3
backups, so a rollover renames server.log to server.log.1 and creates a new
server.log at a new inode, and a held fd keeps reading the renamed file, which
never grows again.

Worse, on Windows it prevents rotation. An open handle makes os.rename fail with
WinError 32, so a tailer holding the log open would break the server's own
logging rather than merely miss it. Measured, not assumed: holding an fd and
renaming raises PermissionError in test_a_tail_must_not_block_rotation.

So this opens, reads from a remembered offset, and closes on every poll. The
extra syscalls cost nothing next to a poll interval, and nothing is held.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MAX_READ = 1 << 20


def _identity(path: Path) -> tuple[int, int, int] | None:
    """The (device, inode, size) that says whether this is still the same file."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_dev, st.st_ino, st.st_size)


@dataclass
class LogTail:
    """Yields new lines from a rotating log, following it across replacements."""

    path: Path
    from_start: bool = False
    _offset: int = field(default=0, init=False)
    _key: tuple[int, int] | None = field(default=None, init=False)
    _partial: str = field(default="", init=False)
    _started: bool = field(default=False, init=False)

    def close(self) -> None:
        """Here for symmetry; nothing is held open between polls."""
        self._partial = ""

    def poll(self) -> list[str]:
        """Return whatever complete lines appeared since the last call."""
        ident = _identity(self.path)
        if ident is None:
            # A file that does not exist yet has no history worth skipping, so
            # the first poll counts as started even when it finds nothing.
            self._started = True
            return []
        dev, ino, size = ident
        key = (dev, ino)

        if not self._started:
            # The log already existed when tailing began, so skip what is there.
            self._offset = 0 if self.from_start else size
            self._key = key
            self._started = True
        elif self._key is None:
            # It appeared after tailing began, so every line in it is new.
            self._offset = 0
            self._key = key
        elif key != self._key:
            # A different file now answers to this path, so read it whole.
            self._offset = 0
            self._key = key
            self._partial = ""
        elif size < self._offset:
            # Same file, truncated in place, which is the other way logs reset.
            self._offset = 0
            self._partial = ""

        if size <= self._offset:
            return []

        try:
            fd = os.open(self.path, os.O_RDONLY)
        except OSError:
            return []
        try:
            os.lseek(fd, self._offset, os.SEEK_SET)
            data = os.read(fd, min(MAX_READ, size - self._offset))
        except OSError:
            return []
        finally:
            os.close(fd)

        if not data:
            return []
        self._offset += len(data)

        text = self._partial + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        # Whatever follows the last newline is unfinished, so hold it for later.
        self._partial = lines.pop()
        return lines
