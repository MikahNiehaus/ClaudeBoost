"""Personalized PageRank must be a tiebreaker, not a re-ranker.

The scoring comment in search.py claimed "a directly connected neighbour
still beats a distant one that merely sits in a busy neighbourhood". It was
measurably false: with PPR_MAX_BOOST at 0.5 a 2 hop hub scored 0.8505 while
the 1 hop direct neighbour scored 0.7902.

These tests assert the observable ranking contract, not the arithmetic:
structural evidence (relation strength and hop distance) decides the order,
and centrality only separates results that structure leaves tied.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server.search as search_mod  # noqa: E402
from server.graph_store import GraphEdge, SQLiteGraphStore  # noqa: E402
from server.search import DEFAULT_EDGE_WEIGHT, DEPTH_DECAY, EDGE_WEIGHTS  # noqa: E402


@dataclass
class FakeResult:
    content: str
    metadata: dict
    score: float


@dataclass
class FakeChunk:
    content: str
    metadata: dict = field(default_factory=dict)


class FakeStore:
    """Stands in for ChromaStore: fixed seed hits, one chunk per file.

    A context manager, like the real one: search.py opens its store in a `with`
    so the shared sqlite handle is checked back in on the raising path too, and a
    double that cannot be entered would only be testing a different function
    than the one that runs.
    """

    def __init__(self, seed_hits):
        self._seed_hits = seed_hits

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None

    def collection_exists(self, name):
        return True

    def search(self, collection, query_embedding, limit=3, min_score=0.1):
        return self._seed_hits[:limit]

    def get_by_source(self, collection, file):
        return [FakeChunk(content=f"content of {file}")]


class FakeEmbedder:
    model_name = "fake-model"

    def embed_query(self, query):
        return [0.0] * 8


def graph_search(monkeypatch, tmp_path, edges, seed_file, seed_score=0.9, depth=2):
    """Drive the real _search_project_graph over a real graph.db."""
    index_dir = tmp_path / "proj"
    (index_dir / "chroma").mkdir(parents=True, exist_ok=True)

    store = SQLiteGraphStore(str(index_dir / "graph.db"))
    store.add_edges([
        GraphEdge(source_file=s, source_symbol="", target_file=t,
                  target_symbol="", edge_type=et, confidence="EXTRACTED")
        for s, t, et in edges
    ])

    seed_hit = FakeResult("seed content", {"source_file": seed_file}, seed_score)
    monkeypatch.setattr(search_mod, "ChromaStore", lambda persist_dir: FakeStore([seed_hit]))
    monkeypatch.setattr(search_mod, "resolve_project_dir", lambda base, root: index_dir)
    monkeypatch.setattr(search_mod, "DATABASES_DIR", tmp_path)

    results = search_mod._search_project_graph(
        "query", str(tmp_path / "src"), FakeEmbedder(),
        limit=50, min_score=0.0, meta_out={}, depth=depth, direction="both",
    )
    # Order, not score. `score` is deliberately the pure structural number now
    # (edge weight times hop decay); centrality is fused in at the rank level,
    # so position is where its effect is visible and score is where it is not.
    return [r["file"] for r in results]


#: The inversion case: one weak direct neighbour against one distant, very
#: central hub, which is where centrality used to outrank hop distance.
HOP_INVERSION_EDGES = [
    ("seed.py", "leaf.py", "calls"),
    ("seed.py", "hub_gateway.py", "calls"),
    ("hub_gateway.py", "hub.py", "imports"),
    ("seed.py", "hub_gateway2.py", "calls"),
    ("hub_gateway2.py", "hub.py", "imports"),
] + [
    edge
    for i in range(200)
    for edge in (
        (f"sat{i}.py", "hub.py", "imports"),
        ("hub.py", f"sat{i}.py", "imports"),
        (f"sat{i}.py", "hub_gateway.py", "imports"),
    )
]


class TestHopDistanceSurvivesCentrality:
    def test_a_direct_neighbour_beats_a_distant_hub(self, monkeypatch, tmp_path):
        """The measured regression: leaf.py 0.7902 vs hub.py 0.8505.

        leaf.py is 1 hop out and structurally isolated. hub.py is 2 hops out
        through a gateway and is the most central node in the graph. Structure
        has to win.
        """
        order = graph_search(monkeypatch, tmp_path, HOP_INVERSION_EDGES, "seed.py")

        assert "leaf.py" in order and "hub.py" in order, order
        assert order.index("leaf.py") < order.index("hub.py"), (
            f"a 2 hop hub outranked a 1 hop direct neighbour: {order[:5]}"
        )

    def test_relation_strength_survives_centrality(self, monkeypatch, tmp_path):
        """Same hop count, different edge type: the stronger relation wins even
        when the weaker one is far more central."""
        edges = [
            ("seed.py", "weak_but_central.py", "calls"),
            ("seed.py", "strong_but_isolated.py", "imports"),
        ] + [
            edge
            for i in range(100)
            for edge in (
                (f"sat{i}.py", "weak_but_central.py", "imports"),
                ("weak_but_central.py", f"sat{i}.py", "imports"),
            )
        ]
        order = graph_search(monkeypatch, tmp_path, edges, "seed.py", depth=1)

        assert order.index("strong_but_isolated.py") < order.index(
            "weak_but_central.py"
        ), order


class TestCentralityStillBreaksTies:
    def test_the_more_central_of_two_equal_neighbours_wins(self, monkeypatch, tmp_path):
        """Fusing must not turn the feature off. Two neighbours with the same
        relation at the same hop are a genuine tie on structure alone, and that
        is exactly where centrality is allowed to decide the order."""
        edges = [
            ("seed.py", "central.py", "imports"),
            ("seed.py", "lonely.py", "imports"),
        ] + [
            edge
            for i in range(50)
            for edge in (
                (f"sat{i}.py", "central.py", "imports"),
                ("central.py", f"sat{i}.py", "imports"),
            )
        ]
        order = graph_search(monkeypatch, tmp_path, edges, "seed.py", depth=1)

        assert order.index("central.py") < order.index("lonely.py"), order
