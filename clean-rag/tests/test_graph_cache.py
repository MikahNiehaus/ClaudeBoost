"""The built graph is cached per project, and the cache cannot go stale.

Measured before caching: 0.2746s average per query on a 4500 node / 45000
edge graph, worst 0.6106s, of which 62% was fetching every edge and
rebuilding the nx.DiGraph from scratch on every single search.

The danger in fixing that is a cache that misses a reindex, which would rank
against a stale graph forever. The reindex runs in a SEPARATE process from
the server doing the searching, so these tests exercise out of process style
mutation directly against the store.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import graph_store as gs  # noqa: E402
from server.graph_store import (  # noqa: E402
    GraphEdge,
    SQLiteGraphStore,
    compute_personalized_pagerank,
    evict_graph_cache,
)

pytest.importorskip("networkx")


@pytest.fixture(autouse=True)
def clean_cache():
    """No cross test bleed through a module level cache."""
    gs._graph_cache.clear()
    yield
    gs._graph_cache.clear()


def edge(source, target):
    return GraphEdge(source_file=source, source_symbol="", target_file=target,
                     target_symbol="", edge_type="imports", confidence="EXTRACTED")


def store_with(tmp_path, pairs, name="graph.db"):
    store = SQLiteGraphStore(str(tmp_path / name))
    store.add_edges([edge(s, t) for s, t in pairs])
    return store


class TestTheCacheActuallySavesTheWork:
    def test_an_unchanged_graph_is_not_refetched_per_query(self, tmp_path, monkeypatch):
        """get_all_edges is the expensive half. It must be paid once, not once
        per search."""
        store = store_with(tmp_path, [("a.py", "b.py"), ("b.py", "c.py")])

        calls = []
        real = store.get_all_edges
        monkeypatch.setattr(store, "get_all_edges",
                            lambda: (calls.append(1), real())[1])

        for _ in range(5):
            assert compute_personalized_pagerank(store, ["a.py"])

        assert len(calls) == 1, f"rebuilt the graph {len(calls)} times for 5 queries"

    def test_each_project_keeps_its_own_graph(self, tmp_path):
        """Two projects must not share a cache entry keyed on anything they
        have in common."""
        one = store_with(tmp_path, [("a.py", "b.py")], name="one.db")
        two = store_with(tmp_path, [("x.py", "y.py")], name="two.db")

        ranks_one = compute_personalized_pagerank(one, ["a.py"])
        ranks_two = compute_personalized_pagerank(two, ["x.py"])

        assert set(ranks_one) == {"a.py", "b.py"}
        assert set(ranks_two) == {"x.py", "y.py"}


class TestTheCacheCannotGoStale:
    def test_a_reindex_that_keeps_the_edge_count_is_still_seen(self, tmp_path):
        """The adversarial case for a naive key.

        An incremental reindex is delete_edges_for_file() then add_edges().
        A file whose new version has the SAME number of edges leaves
        count_edges() identical, and WAL means graph.db's own mtime and size
        never moved either. The ranks must still describe the new graph.
        """
        store = store_with(tmp_path, [("a.py", "b.py"), ("a.py", "c.py")])

        before = compute_personalized_pagerank(store, ["a.py"])
        assert before.get("b.py", 0) > 0
        assert "X.py" not in before

        store.delete_edges_for_file("a.py")
        store.add_edges([edge("a.py", "X.py"), edge("a.py", "Y.py")])
        assert store.count_edges() == 2, "the count must be unchanged for this test"

        after = compute_personalized_pagerank(store, ["a.py"])
        assert after.get("X.py", 0) > 0, (
            f"ranked against a stale graph: {after}"
        )
        assert "b.py" not in after, f"a deleted edge is still ranked: {after}"

    def test_growing_the_graph_is_seen(self, tmp_path):
        store = store_with(tmp_path, [("a.py", "b.py")])
        assert "c.py" not in compute_personalized_pagerank(store, ["a.py"])

        store.add_edges([edge("b.py", "c.py")])
        assert "c.py" in compute_personalized_pagerank(store, ["a.py"])

    def test_a_force_rebuild_that_replaces_graph_db_is_seen(self, tmp_path):
        """force=True unlinks graph.db and builds a new one
        (indexing._init_graph_store). The multi day reindex does this to every
        project, so missing it would leave the server ranking every search
        against a graph that no longer exists.

        Hardest version of the case: the rebuild reproduces the SAME edge
        count and the SAME sequence value, so only the file identity differs.
        """
        import gc

        db = tmp_path / "graph.db"
        store = store_with(tmp_path, [("a.py", "b.py"), ("a.py", "c.py")])
        assert "b.py" in compute_personalized_pagerank(store, ["a.py"])

        del store
        gc.collect()  # release handles so the unlink can succeed on Windows
        db.unlink()

        rebuilt = SQLiteGraphStore(str(db))
        rebuilt.add_edges([edge("a.py", "P.py"), edge("a.py", "Q.py")])
        assert rebuilt.row_signature() == (2, 2), (
            "this test is only meaningful when the row signature is unchanged"
        )

        after = compute_personalized_pagerank(rebuilt, ["a.py"])
        assert "P.py" in after, f"ranked against the deleted graph: {after}"
        assert "b.py" not in after, f"ranked against the deleted graph: {after}"

    def test_read_traffic_alone_does_not_invalidate(self, tmp_path):
        """The key must not move when nothing was written.

        WAL sidecar stat was rejected for exactly this: connections are closed
        by the garbage collector at unpredictable times and the last close
        checkpoints the WAL away, which moved the key on read-only traffic.
        """
        import gc

        store = store_with(tmp_path, [("a.py", "b.py"), ("b.py", "c.py")])
        first = compute_personalized_pagerank(store, ["a.py"])

        calls = []
        real = store.get_all_edges
        store.get_all_edges = lambda: (calls.append(1), real())[1]

        for _ in range(5):
            store.count_edges()
            gc.collect()
            assert compute_personalized_pagerank(store, ["a.py"]) == first

        assert calls == [], f"read traffic caused {len(calls)} needless rebuilds"

    def test_a_second_store_object_on_the_same_db_shares_the_graph(self, tmp_path):
        """The server builds a new SQLiteGraphStore per search, so the cache
        keys on the database path, not the object."""
        store_with(tmp_path, [("a.py", "b.py")])

        first = SQLiteGraphStore(str(tmp_path / "graph.db"))
        assert compute_personalized_pagerank(first, ["a.py"])

        second = SQLiteGraphStore(str(tmp_path / "graph.db"))
        calls = []
        real = second.get_all_edges
        second.get_all_edges = lambda: (calls.append(1), real())[1]

        assert compute_personalized_pagerank(second, ["a.py"])
        assert calls == [], "a fresh store object missed the cache"


class TestEviction:
    def test_evicting_forces_a_rebuild_without_changing_the_answer(self, tmp_path):
        store = store_with(tmp_path, [("a.py", "b.py")])
        before = compute_personalized_pagerank(store, ["a.py"])

        evict_graph_cache(tmp_path / "graph.db")

        calls = []
        real = store.get_all_edges
        store.get_all_edges = lambda: (calls.append(1), real())[1]
        after = compute_personalized_pagerank(store, ["a.py"])

        assert calls == [1], "eviction did not force a rebuild"
        assert after == before

    def test_evicting_an_uncached_project_is_harmless(self, tmp_path):
        evict_graph_cache(tmp_path / "never-cached.db")

    def test_release_project_resources_evicts_the_graph(self, tmp_path, monkeypatch):
        """The house pattern: per project handles get dropped in one place, so
        the graph has to be dropped there too rather than pinning 6 MB per
        project for the life of the process."""
        from server import reindex_unit

        databases = tmp_path / "databases"
        project_dir = databases / "_projects" / "pid123"
        project_dir.mkdir(parents=True)
        (project_dir / "chroma").mkdir()

        store = store_with(project_dir, [("a.py", "b.py")])
        assert compute_personalized_pagerank(store, ["a.py"])
        assert len(gs._graph_cache) == 1

        monkeypatch.setattr("server.config.DATABASES_DIR", databases)
        reindex_unit.release_project_resources("pid123")

        assert len(gs._graph_cache) == 0, "release_project_resources left the graph cached"


class TestTheCacheIsBounded:
    def test_it_does_not_grow_with_the_project_count(self, tmp_path):
        """16 projects are registered and a 4500 node graph measured 6.2 MB.
        An unbounded dict would hold all of them in the server process."""
        for i in range(gs._GRAPH_CACHE_MAX + 3):
            store = store_with(tmp_path, [(f"a{i}.py", f"b{i}.py")], name=f"g{i}.db")
            compute_personalized_pagerank(store, [f"a{i}.py"])

        assert len(gs._graph_cache) <= gs._GRAPH_CACHE_MAX

    def test_the_evicted_entry_is_the_least_recently_used(self, tmp_path):
        stores = []
        for i in range(gs._GRAPH_CACHE_MAX):
            store = store_with(tmp_path, [(f"a{i}.py", f"b{i}.py")], name=f"g{i}.db")
            compute_personalized_pagerank(store, [f"a{i}.py"])
            stores.append(store)

        # Touch the oldest so it is no longer the LRU victim.
        compute_personalized_pagerank(stores[0], ["a0.py"])

        overflow = store_with(tmp_path, [("z.py", "w.py")], name="overflow.db")
        compute_personalized_pagerank(overflow, ["z.py"])

        cached = {Path(k).name for k in gs._graph_cache}
        assert "g0.db" in cached, "evicted the entry that was just used"
        assert "g1.db" not in cached, "did not evict the least recently used entry"
