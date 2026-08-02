"""Tests for the graph retrieval improvements: RRF fusion and personalized PageRank.

Behavioral. What matters is that fusion stops comparing incomparable scores and
that PageRank is finally query relative, not that either is spelled a
particular way.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.search import reciprocal_rank_fusion  # noqa: E402


def _r(file, line=0, score=0.5, **extra):
    return {"file": file, "line_start": line, "score": score, **extra}


class TestReciprocalRankFusion:
    def test_a_result_in_both_lists_beats_one_in_either_alone(self):
        """The entire point of running both retrieval modes: agreement is
        evidence."""
        vec = [_r("only_vector.py"), _r("in_both.py")]
        graph = [_r("only_graph.py"), _r("in_both.py")]
        fused = reciprocal_rank_fusion(vec, graph)
        assert fused[0]["file"] == "in_both.py"

    def test_ranking_ignores_the_raw_score_scale(self):
        """A cosine similarity and a graph product are different units.

        The old merge kept whichever float was bigger, so a scoring change on
        one side silently took over the whole result set.
        """
        vec = [_r("vector_top.py", score=0.01)]      # tiny numbers
        graph = [_r("graph_top.py", score=999.0)]     # huge numbers
        fused = reciprocal_rank_fusion(vec, graph)
        # Both are rank 1 in their own list, so they tie. The 999 must not win.
        assert fused[0]["rrf_score"] == fused[1]["rrf_score"], (
            "fusion is being influenced by the raw score scale"
        )

    def test_rank_order_within_a_list_is_preserved(self):
        vec = [_r("first.py"), _r("second.py"), _r("third.py")]
        fused = reciprocal_rank_fusion(vec)
        assert [r["file"] for r in fused] == ["first.py", "second.py", "third.py"]

    def test_same_file_different_lines_are_distinct_results(self):
        vec = [_r("a.py", line=10), _r("a.py", line=99)]
        assert len(reciprocal_rank_fusion(vec)) == 2

    def test_the_richer_record_survives_a_merge(self):
        """Graph results carry relation and seed_file; losing them loses the
        explanation of why a file was returned."""
        vec = [_r("shared.py")]
        graph = [_r("shared.py", relation="imports", seed_file="seed.py")]
        fused = reciprocal_rank_fusion(vec, graph)
        assert len(fused) == 1
        assert fused[0]["relation"] == "imports"
        assert fused[0]["seed_file"] == "seed.py"

    def test_empty_inputs(self):
        assert reciprocal_rank_fusion([], []) == []
        assert reciprocal_rank_fusion() == []

    def test_one_empty_list_does_not_discard_the_other(self):
        assert len(reciprocal_rank_fusion([_r("a.py")], [])) == 1

    def test_k_damps_the_advantage_of_the_top_slot(self):
        """With the standard k=60, first vs second place is a small edge, not a
        landslide. A tiny k would let one list dictate the whole ordering."""
        fused = reciprocal_rank_fusion([_r("a.py"), _r("b.py")])
        ratio = fused[0]["rrf_score"] / fused[1]["rrf_score"]
        assert ratio < 1.05, f"top slot dominates too heavily: {ratio}"

    def test_every_result_carries_a_fused_score(self):
        fused = reciprocal_rank_fusion([_r("a.py")], [_r("b.py")])
        assert all("rrf_score" in r for r in fused)


class TestStructureAndCentralityAreFusedNotMultiplied:
    """PageRank and an edge weight product share no scale.

    Multiplying them was the original attempt and it inverted hop distance: a
    2 hop hub scored 0.8505 against a direct neighbour's 0.7902. Capping the
    multiplier fixed that but needed a bespoke derivation to prove the bound.
    Fusing by rank needs no bound because it never touches the raw numbers,
    which is the same argument reciprocal_rank_fusion already makes for the
    vector versus graph merge.
    """

    @staticmethod
    def _fuse(by_structure, by_centrality):
        """Mirrors how _search_project_graph fuses, weights included."""
        from server.search import CENTRALITY_WEIGHT

        return [
            r["file"] for r in reciprocal_rank_fusion(
                [{"file": f} for f in by_structure],
                [{"file": f} for f in by_centrality],
                key=lambda r: r["file"],
                weights=(1.0, CENTRALITY_WEIGHT),
            )
        ]

    def test_structure_alone_decides_when_centrality_is_unavailable(self):
        """PageRank failing must degrade to the previous ordering, not scramble
        it. An empty second list has to be inert."""
        assert self._fuse(["a.py", "b.py", "c.py"], []) == ["a.py", "b.py", "c.py"]

    def test_agreement_between_the_two_wins(self):
        """A file both structurally close and centrally placed is the best
        evidence available."""
        order = self._fuse(["agreed.py", "struct.py"], ["agreed.py", "central.py"])
        assert order[0] == "agreed.py"

    def test_centrality_cannot_promote_a_file_structure_ranked_last(self):
        """The evidence is still proximity. Being central must not drag a
        distant file over a much closer one."""
        by_structure = [f"close{i}.py" for i in range(8)] + ["distant.py"]
        by_centrality = ["distant.py"]
        order = self._fuse(by_structure, by_centrality)
        assert order.index("close0.py") < order.index("distant.py")

    def test_centrality_breaks_a_tie_between_adjacent_files(self):
        """What PageRank is actually for: two files the structure ranks next to
        each other, and centrality says which matters here."""
        order = self._fuse(["x.py", "y.py"], ["y.py"])
        assert order[0] == "y.py"

    def test_a_file_in_neither_list_does_not_appear(self):
        assert "ghost.py" not in self._fuse(["a.py"], ["b.py"])

    def test_ordering_is_deterministic(self):
        args = (["a.py", "b.py", "c.py"], ["c.py", "a.py"])
        assert self._fuse(*args) == self._fuse(*args)


class TestPersonalizedPageRankIsQueryRelative:
    """The actual claim: seeding changes the answer. A global score cannot."""

    def _store(self, tmp_path, edges):
        from server.graph_store import GraphEdge, SQLiteGraphStore

        store = SQLiteGraphStore(str(tmp_path / "graph.db"))
        store.add_edges([
            GraphEdge(
                source_file=s, source_symbol="", target_file=t, target_symbol="",
                edge_type="imports", confidence="EXTRACTED",
            )
            for s, t in edges
        ])
        return store

    def test_different_seeds_produce_different_rankings(self, tmp_path):
        from server.graph_store import compute_personalized_pagerank

        # Two clusters joined by a single bridge.
        store = self._store(tmp_path, [
            ("a1.py", "a2.py"), ("a2.py", "a3.py"), ("a3.py", "a1.py"),
            ("b1.py", "b2.py"), ("b2.py", "b3.py"), ("b3.py", "b1.py"),
            ("a3.py", "b1.py"),
        ])

        from_a = compute_personalized_pagerank(store, ["a1.py"])
        from_b = compute_personalized_pagerank(store, ["b1.py"])
        if not from_a or not from_b:
            pytest.skip("networkx unavailable")

        a_cluster = sum(from_a.get(f, 0) for f in ("a1.py", "a2.py", "a3.py"))
        b_cluster = sum(from_b.get(f, 0) for f in ("b1.py", "b2.py", "b3.py"))
        assert a_cluster > sum(from_a.get(f, 0) for f in ("b1.py", "b2.py", "b3.py"))
        assert b_cluster > sum(from_b.get(f, 0) for f in ("a1.py", "a2.py", "a3.py"))

    def test_no_seeds_returns_nothing_rather_than_a_global_score(self, tmp_path):
        """An empty seed set must not silently degrade into global PageRank,
        which is the exact score this replaces."""
        from server.graph_store import compute_personalized_pagerank

        store = self._store(tmp_path, [("a.py", "b.py")])
        assert compute_personalized_pagerank(store, []) == {}

    def test_a_seed_absent_from_the_graph_does_not_raise(self, tmp_path):
        """networkx raises if personalization names a node it does not have.
        A brand new file, or one in a language with no parser, hits this."""
        from server.graph_store import compute_personalized_pagerank

        store = self._store(tmp_path, [("a.py", "b.py")])
        assert compute_personalized_pagerank(store, ["nowhere.py"]) == {}

    def test_empty_graph_does_not_raise(self, tmp_path):
        from server.graph_store import compute_personalized_pagerank

        store = self._store(tmp_path, [])
        assert compute_personalized_pagerank(store, ["a.py"]) == {}
