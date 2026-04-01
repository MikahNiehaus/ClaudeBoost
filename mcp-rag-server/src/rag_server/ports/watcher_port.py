"""Abstract interface for file system watching."""

from abc import ABC, abstractmethod
from typing import Callable


class WatcherPort(ABC):
    """Port for file system change detection."""

    @abstractmethod
    def watch(self, paths: list[str], on_change: Callable[[str], None]) -> None:
        """Start watching paths. Calls on_change(file_path) when files change."""
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop watching."""
        ...
