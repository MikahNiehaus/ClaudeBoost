"""Community detection over the code graph.

Uses graspologic Leiden if available, falls back to networkx Leiden (built into
networkx 3.x), then falls back to greedy modularity. One of these always works.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rag_server.adapters.sqlite_graph_store import SQLiteGraphStore

logger = logging.getLogger(__name__)


def detect_communities(graph_store: "SQLiteGraphStore") -> dict[str, int]:
    """Partition files into communities.

    Tries graspologic Leiden first, then networkx Leiden, then networkx greedy
    modularity. Returns a mapping of file path → community_id, or {} on failure.
    """
    edges = graph_store.get_all_edges()
    if not edges:
        logger.info("Community detection skipped: no edges in graph")
        return {}

    try:
        G = _build_nx_graph(edges)
        if G.number_of_nodes() == 0:
            return {}

        # graspologic Leiden — most accurate, optional dep
        try:
            from graspologic.partition import leiden as _graspologic_leiden
            partition = _graspologic_leiden(G)
            logger.info("Community detection: graspologic Leiden, %d nodes", G.number_of_nodes())
            return dict(partition)
        except ImportError:
            pass

        # networkx greedy modularity — native, always available, no backend deps
        from networkx.algorithms.community import greedy_modularity_communities
        communities = list(greedy_modularity_communities(G))
        mapping = {}
        for cid, members in enumerate(communities):
            for node in members:
                mapping[node] = cid
        logger.info(
            "Community detection: networkx greedy modularity, %d nodes -> %d communities",
            G.number_of_nodes(), len(communities),
        )
        return mapping

    except Exception:
        logger.exception("Community detection failed")
        return {}


def compute_pagerank(graph_store: "SQLiteGraphStore") -> dict[str, float]:
    """Score each file by how many other files import or reference it.

    Uses PageRank on a directed graph where A→B means A imports/references B,
    so widely-imported files (core modules, shared utilities) get high scores.
    Returns {} on any failure or if NetworkX is not available.
    """
    try:
        import networkx as nx
    except ImportError:
        logger.debug("PageRank skipped: networkx not installed")
        return {}

    edges = graph_store.get_all_edges()
    if not edges:
        return {}

    try:
        G: nx.DiGraph = nx.DiGraph()
        for e in edges:
            G.add_node(e.source_file)
            if e.target_file and e.target_file not in ("_external_", ""):
                G.add_node(e.target_file)
                G.add_edge(e.source_file, e.target_file)
        if G.number_of_nodes() == 0:
            return {}
        scores = nx.pagerank(G, alpha=0.85, max_iter=100)
        logger.info("PageRank computed for %d nodes", len(scores))
        return scores
    except Exception:
        logger.exception("PageRank computation failed")
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
        if e.target_file and e.target_file != "_external_":
            G.add_node(e.target_file)
            G.add_edge(e.source_file, e.target_file)

    return G
