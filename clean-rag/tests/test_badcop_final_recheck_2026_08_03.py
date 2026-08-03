"""bad-cop FINAL adversarial re-check (round 4), NOT part of the reviewed diff.

Targets the two attack angles from the task that were "dismissed as inert"
or only argued from code-reading, and forces them through real execution
instead of accepting the reasoning a third time:

1. node_pagerank staleness on a deleted file -- proves BOTH halves: a stale
   row really does survive delete_edges_referencing_file, AND that stale row
   is genuinely unreachable through get_neighbours()'s only consumer of
   get_all_pagerank() (the _prune() frontier-trim), because a deleted file's
   edges are gone so it can never enter a frontier to begin with.

2. The manifest-checkpoint interval throttle under a REAL (non-injected)
   clock, not _FakeClock. test_manifest_checkpoint_and_deletion.py only
   proves the interval arithmetic against a stepped fake; this drives
   time.sleep for real between synthetic files so a change that broke the
   throttle's use of the real monotonic clock (as opposed to the fake one
   the other suite substitutes) would still be caught.
"""

import hashlib
import math
import sys
import time
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server import indexing  # noqa: E402
from server.graph_store import SQLiteGraphStore  # noqa: E402

COLLECTION = "codebase"


class StubEmbedder:
    model_name = "stub-embedder"
    _DIM = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._DIM
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self._DIM] += 1.0 if (h // self._DIM) % 2 == 0 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def _project(root: Path, n_files: int = 6) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        header = f"import os\nimport json\nfrom module_{(f + 1) % n_files:02d} import helper\n"
        body = header + "\n".join(
            f'''
def handler_{f}_{i}(payload, retries=3):
    """Process one payload and return a normalised record."""
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    if total > 1000 and retries > 0:
        return handler_{f}_{i}({{"items": []}}, retries - 1)
    return {{"total": total, "count": len(payload.get("items", []))}}
'''
            for i in range(4)
        )
        (root / f"module_{f:02d}.py").write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
    project = _project(tmp_path / "proj")
    paths = indexing._project_paths(str(project))
    return project, paths


# ---------------------------------------------------------------------------
# node_pagerank staleness
# ---------------------------------------------------------------------------

def test_stale_pagerank_row_really_survives_deletion(rig):
    """Half 1: delete_edges_referencing_file does NOT touch node_pagerank.

    If this fails (row gets cleared), the "dismissed as inert" reasoning is
    moot anyway since there'd be nothing stale left to worry about.
    """
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    store = SQLiteGraphStore(str(graph_db))
    before_pr = store.get_all_pagerank()
    assert "module_00.py" in before_pr, (
        "fixture must have a real pagerank score for module_00.py, or this "
        "proves nothing"
    )

    (project / "module_00.py").unlink()
    indexing.reindex_file(str(project), str(project / "module_00.py"), StubEmbedder())

    after_pr = SQLiteGraphStore(str(graph_db)).get_all_pagerank()
    assert "module_00.py" in after_pr, (
        "the stale row was actually cleared -- the staleness claim under "
        "test is false, re-examine on different grounds"
    )
    assert after_pr["module_00.py"] == before_pr["module_00.py"]


def test_stale_pagerank_row_is_unreachable_through_get_neighbours(rig):
    """Half 2: even though the row survives, it can never be read.

    get_all_pagerank() has exactly one call site, _prune(), which only ever
    ranks a FRONTIER already derived from live edges. A deleted file has
    zero edges left, so it can never appear as a frontier candidate at any
    hop, at any max_nodes setting -- forced here with max_nodes=1 so pruning
    is guaranteed to trigger on every hop if there's anything to prune.
    """
    project, (_root, _pid, index_dir, _chroma, _manifest) = rig
    indexing.index_project(str(project), StubEmbedder(), force=True)
    graph_db = index_dir / "graph.db"

    (project / "module_00.py").unlink()
    indexing.reindex_file(str(project), str(project / "module_00.py"), StubEmbedder())

    store = SQLiteGraphStore(str(graph_db))
    assert "module_00.py" in store.get_all_pagerank(), (
        "precondition failed: no stale row to try to leak through pruning"
    )

    # Walk from every surviving file, forcing pruning at every hop.
    surviving = [f"module_{i:02d}.py" for i in range(1, 6)]
    seen_files: set[str] = set()
    for seed in surviving:
        edges = store.get_neighbours(seed, depth=5, max_nodes=1)
        for e in edges:
            seen_files.add(e.source_file)
            seen_files.add(e.target_file)

    assert "module_00.py" not in seen_files, (
        "a stale pagerank row for a deleted file leaked into a live graph "
        "traversal result -- the 'dismissed as inert' claim is false"
    )


# ---------------------------------------------------------------------------
# Real-clock checkpoint throttle (no _FakeClock)
# ---------------------------------------------------------------------------

def test_checkpoint_throttle_holds_under_the_real_monotonic_clock(rig, monkeypatch):
    """The existing suite proves the interval arithmetic against a stepped
    fake clock. This drives real time.sleep between files instead, so a
    change that broke the real time.monotonic() plumbing specifically
    (as opposed to the interval math) would still be caught.
    """
    project, (_root, _pid, _idx, _chroma, manifest_path) = rig
    interval = 0.2
    monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", interval)

    real_embed = StubEmbedder.embed

    class SlowEmbedder(StubEmbedder):
        def embed(self, texts):
            time.sleep(0.08)  # real wall-clock delay per file
            return real_embed(self, texts)

    fired_at: list[float] = []
    real_save = indexing._save_project_manifest

    def spy(*args, **kwargs):
        if kwargs.get("incomplete") is True:
            fired_at.append(time.monotonic())
        return real_save(*args, **kwargs)

    monkeypatch.setattr(indexing, "_save_project_manifest", spy)
    indexing.index_project(str(project), SlowEmbedder(), force=True)

    assert len(fired_at) >= 2, (
        f"need at least two real-clock checkpoints to measure a gap, got "
        f"{fired_at} -- increase file count or sleep if this is flaky"
    )
    gaps = [b - a for a, b in zip(fired_at, fired_at[1:])]
    assert all(g >= interval - 0.01 for g in gaps), (
        f"real-clock checkpoints fired {gaps}s apart against a {interval}s "
        f"interval -- the throttle does not hold under a real clock"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
