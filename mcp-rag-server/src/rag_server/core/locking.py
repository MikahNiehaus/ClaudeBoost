"""Cross-process file lock for serializing RAG index writes.

Without coordination, two Claude Code instances sharing the same ChromaDB SQLite
files can hit NotFoundError or empty results during the delete→create→populate
window of a force reindex. This module serializes writes and lets readers wait.

Writers:
    with index_write_lock(RAG_INDEX_DIR / "index.lock"):
        ...

Readers (check before returning empty):
    if is_write_locked(lock_path):
        ...
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_WRITE_LOCK_TIMEOUT = 120  # seconds — a full reindex finishes well within this
_POLL_INTERVAL = 0.2       # seconds between lock acquisition retries
_LOCK_WARN_AFTER = 5       # log a warning if still waiting after this many seconds

# Per-path threading locks prevent the same process from deadlocking against
# itself (e.g. file watcher calling index_all while a manual rag_index runs).
_thread_locks: dict[str, threading.Lock] = {}
_thread_locks_guard = threading.Lock()


def _get_thread_lock(lock_path: Path) -> threading.Lock:
    key = str(lock_path.resolve())
    with _thread_locks_guard:
        if key not in _thread_locks:
            _thread_locks[key] = threading.Lock()
        return _thread_locks[key]


class _IndexWriteLock:
    """Context manager: intra-process thread lock + cross-process file lock."""

    def __init__(self, lock_path: Path):
        self._lock_path = lock_path
        self._thread_lock = _get_thread_lock(lock_path)
        self._file_lock: "_FileLock | None" = None

    def __enter__(self):
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock.acquire()
        logger.debug("Waiting for index file lock: %s", self._lock_path)
        if sys.platform == "win32":
            self._file_lock = _WinFileLock(self._lock_path)
        else:
            self._file_lock = _UnixFileLock(self._lock_path)
        self._file_lock.__enter__()
        logger.debug("Acquired index write lock: %s", self._lock_path)
        return self

    def __exit__(self, *_):
        if self._file_lock is not None:
            self._file_lock.__exit__(None, None, None)
            self._file_lock = None
        self._thread_lock.release()
        logger.debug("Released index write lock: %s", self._lock_path)


def index_write_lock(lock_path: Path) -> _IndexWriteLock:
    """Return a context manager that holds an exclusive cross-process write lock.

    Blocks until the lock is available or _WRITE_LOCK_TIMEOUT seconds pass.
    The OS releases the file lock automatically if the process exits or crashes.
    """
    return _IndexWriteLock(lock_path)


def is_write_locked(lock_path: Path) -> bool:
    """Return True if the write lock on lock_path is currently held.

    Checks both the intra-process thread lock and the cross-process file lock.
    """
    if not lock_path.exists():
        return False
    thread_lock = _get_thread_lock(lock_path)
    if thread_lock.locked():
        return True  # same process holds it
    # Try a non-blocking file lock acquisition to check cross-process state
    if sys.platform == "win32":
        file_lock: "_FileLock" = _WinFileLock(lock_path, timeout=0)
    else:
        file_lock = _UnixFileLock(lock_path, timeout=0)
    try:
        file_lock.__enter__()
        file_lock.__exit__(None, None, None)
        return False
    except (TimeoutError, OSError):
        return True


class _FileLock:
    """Interface for platform-specific file lock implementations."""

    def __enter__(self) -> "_FileLock": ...
    def __exit__(self, *_): ...


class _UnixFileLock(_FileLock):
    """Exclusive file lock using fcntl.flock (Unix/macOS)."""

    def __init__(self, path: Path, timeout: float = _WRITE_LOCK_TIMEOUT):
        self._path = path
        self._timeout = timeout
        self._f = None

    def __enter__(self):
        import fcntl
        self._f = open(self._path, "w")
        deadline = time.monotonic() + self._timeout if self._timeout > 0 else None
        _wait_start = time.monotonic()
        _warned = False
        while True:
            try:
                fcntl.flock(self._f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                _waited = time.monotonic() - _wait_start
                if deadline is None or time.monotonic() > deadline:
                    self._f.close()
                    self._f = None
                    logger.error(
                        "Timed out waiting %ds for index write lock: %s", int(_waited), self._path
                    )
                    raise TimeoutError(
                        f"Could not acquire index lock after {self._timeout}s: {self._path}"
                    )
                if not _warned and _waited >= _LOCK_WARN_AFTER:
                    logger.warning(
                        "Still waiting for index write lock (%.0fs so far): %s — another process is indexing",
                        _waited, self._path,
                    )
                    _warned = True
                time.sleep(_POLL_INTERVAL)

    def __exit__(self, *_):
        if self._f:
            import fcntl
            try:
                fcntl.flock(self._f, fcntl.LOCK_UN)
            except OSError:
                pass
            self._f.close()
            self._f = None


class _WinFileLock(_FileLock):
    """Exclusive file lock using msvcrt.locking (Windows)."""

    def __init__(self, path: Path, timeout: float = _WRITE_LOCK_TIMEOUT):
        self._path = path
        self._timeout = timeout
        self._fd = None

    def __enter__(self):
        import msvcrt
        self._fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
        deadline = time.monotonic() + self._timeout if self._timeout > 0 else None
        _wait_start = time.monotonic()
        _warned = False
        while True:
            try:
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                return self
            except OSError:
                _waited = time.monotonic() - _wait_start
                if deadline is None or time.monotonic() > deadline:
                    os.close(self._fd)
                    self._fd = None
                    logger.error(
                        "Timed out waiting %ds for index write lock: %s", int(_waited), self._path
                    )
                    raise TimeoutError(
                        f"Could not acquire index lock after {self._timeout}s: {self._path}"
                    )
                if not _warned and _waited >= _LOCK_WARN_AFTER:
                    logger.warning(
                        "Still waiting for index write lock (%.0fs so far): %s — another process is indexing",
                        _waited, self._path,
                    )
                    _warned = True
                time.sleep(_POLL_INTERVAL)

    def __exit__(self, *_):
        if self._fd is not None:
            import msvcrt
            try:
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
