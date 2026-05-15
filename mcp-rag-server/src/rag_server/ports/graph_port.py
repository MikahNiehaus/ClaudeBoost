"""Port for graph store operations — edges extracted from code ASTs."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


@dataclass
class GraphEdge:
    """A directed edge in the code graph.

    source_file / source_symbol → target_file / target_symbol
    edge_type:  "calls" | "imports" | "inherits"
    confidence: "EXTRACTED" (direct AST read) | "INFERRED" (name-match heuristic)
    """
    source_file: str
    source_symbol: str
    target_file: str
    target_symbol: str
    edge_type: str
    confidence: str


class GraphStorePort(ABC):
    """Abstract interface for storing and querying code graph edges."""

    @abstractmethod
    def add_edges(self, edges: Sequence[GraphEdge]) -> None:
        """Persist a batch of edges (duplicates are ignored via INSERT OR IGNORE)."""
        ...

    @abstractmethod
    def get_neighbours(
        self,
        file: str,
        symbol: str | None = None,
        depth: int = 1,
    ) -> list[GraphEdge]:
        """Return edges where source_file or target_file matches *file*.

        If *symbol* is given, also filter by source_symbol or target_symbol.
        *depth* is reserved for future multi-hop traversal (currently depth=1 only).
        Returns an empty list when no edges exist — not an error.
        """
        ...

    @abstractmethod
    def delete_edges_for_file(self, file: str) -> None:
        """Remove all edges where source_file == *file* (used on incremental re-index)."""
        ...

    @abstractmethod
    def has_graph(self) -> bool:
        """Return True if at least one edge has been stored."""
        ...

    @abstractmethod
    def resolve_target_files(self, file_map: dict[str, str]) -> int:
        """Resolve target_file='' edges using the project file map.

        *file_map* maps module-name variants to project-relative file paths,
        e.g. {"foo.bar": "foo/bar.py", "foo/bar": "foo/bar.py"}.
        Updates edges in-place. Returns the count of edges resolved.
        """
        ...
