"""File watcher using watchdog. Cross-platform, Windows 11 compatible."""

import logging
import threading
import time
from typing import Callable

from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
from watchdog.observers import Observer

from rag_server.ports.watcher_port import WatcherPort

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 2.0


class _DebouncedHandler(FileSystemEventHandler):
    """Batches rapid file changes with a debounce window."""

    def __init__(self, on_change: Callable[[str], None]):
        self._on_change = on_change
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_modified(self, event):
        if event.is_directory:
            return
        self._schedule(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._schedule(event.src_path)

    def _schedule(self, path: str):
        with self._lock:
            self._pending[path] = time.time()
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self):
        with self._lock:
            paths = list(self._pending.keys())
            self._pending.clear()
        for path in paths:
            try:
                self._on_change(path)
            except Exception:
                logger.exception("Error handling change for %s", path)


class FileWatcher(WatcherPort):
    """Watches directories for file changes using watchdog."""

    def __init__(self):
        self._observer: Observer | None = None

    def watch(self, paths: list[str], on_change: Callable[[str], None]) -> None:
        handler = _DebouncedHandler(on_change)
        self._observer = Observer()
        for path in paths:
            self._observer.schedule(handler, path, recursive=True)
            logger.info("Watching: %s", path)
        self._observer.daemon = True
        self._observer.start()

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
