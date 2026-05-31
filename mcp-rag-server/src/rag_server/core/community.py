"""Leiden community detection over the code graph.

graspologic is an optional dependency. If not installed, detect_communities
returns {} and logs a warning — indexing continues normally.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore

logger = logging.getLogger(__name__)


def detect_communities(graph_store: "SQLiteGraphStore") -> dict[str, int]:
    """Partition files into communities using the Leiden algorithm.

    Returns a mapping of file path → community_id.
    Returns {} on any failure (missing graspologic, empty graph, error).
    """
    try:
        import networkx as nx  # noqa: F401
        from graspologic.partition import leiden
    except ImportError as e:
        logger.warning("Community detection skipped: %s not installed", e.name)
        return {}

    edges = graph_store.get_all_edges()
    if not edges:
        logger.info("Community detection skipped: no edges in graph")
        return {}

    try:
        G = _build_nx_graph(edges)
        if G.number_of_nodes() == 0:
            return {}

        partition = leiden(G)
        return dict(partition)
    except Exception:
        logger.exception("Community detection failed")
        return {}


def _build_nx_graph(edges):
    """Build an undirected NetworkX graph from GraphEdge objects.

    Isolated nodes (source files with no resolved target) are added as
    zero-degree nodes so Leiden assigns them their own community.
    Unresolved edges (target_file='') are skipped for the edge but the
    source_file node is still added.
    """
    import networkx as nx

    G: nx.Graph = nx.Graph()

    for e in edges:
        G.add_node(e.source_file)
        if e.target_file:
            G.add_node(e.target_file)
            G.add_edge(e.source_file, e.target_file)

    return G
