"""index_project must checkpoint its manifest, and a deleted file must not
force a rebuild.

Two defects, both proven on a real run before these tests existed.

**Checkpointing.** index_project wrote its manifest exactly once, at the very
end. A graceful abort through should_abort still returned normally and so still
saved, marked incomplete, and the next sweep resumed from it. A hard kill saved
nothing at all: every file then read as changed, which tripped
FULL_REINDEX_THRESHOLD, which forced a rebuild from zero. That happened for real
and cost hours of embedding.

The dangerous fix is worse than the bug. A manifest entry is a claim that a
file's chunks are in the store, so a checkpoint written BEFORE the chunks commit
survives a crash as a permanent lie: neither find_changed_files nor the
unchanged hash skip compares against store contents, so nothing ever notices the
file is missing and nothing reindexes it. Late is recoverable, early is silent
data loss, so the ordering is asserted directly here and not just assumed.

**Deletion.** auto_reindex forced a full rebuild whenever any file vanished, on
the stated grounds that stale chunks could not be cleared otherwise. That was
never true of the store: delete_by_source and delete_edges_for_file are plain
SQL deletes on the stored path with no filesystem check. reindex_file simply
returned an error before reaching them. One deleted file therefore cost a
re embed of every other file in the project.
"""

import asyncio
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server import auto_reindex as ar  # noqa: E402
from server import indexing  # noqa: E402
from server.store import ChromaStore  # noqa: E402

COLLECTION = "codebase"


class _FakeClock:
    """Stands in for the `time` module inside indexing.

    monotonic() advances a fixed step per call so the number and spacing of
    checkpoints in a run is arithmetic rather than a race against how fast the
    machine happens to be. time() delegates to the real clock, since the
    elapsed figures in the result dict are not what is under test here.
    """

    def __init__(self, step: float):
        import time as _real

        self._step = step
        self._real = _real
        self.now = 0.0

    def monotonic(self) -> float:
        self.now += self._step
        return self.now

    def time(self) -> float:
        return self._real.time()


class StubEmbedder:
    """Signed hashed bag of words, the same shape the other suites use."""

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


class WatchingEmbedder(StubEmbedder):
    """Reads the manifest off disk on every embed call.

    embed() runs before add_chunks for the file being processed, so each
    observation is a snapshot of what had been checkpointed strictly earlier in
    the run. That is the only way to see mid run state from outside without
    actually killing the process.
    """

    def __init__(self, manifest_path: Path):
        self._manifest_path = manifest_path
        #: (raw text, parsed) pairs. The raw text is kept so a caller can tell
        #: a real checkpoint from the manifest a PREVIOUS run left lying there,
        #: which is otherwise indistinguishable and quietly passes assertions
        #: about content this run never wrote.
        self.observations: list[tuple[str, dict]] = []

    def embed(self, texts):
        if self._manifest_path.exists():
            raw = self._manifest_path.read_text(encoding="utf-8")
            try:
                self.observations.append((raw, json.loads(raw)))
            except json.JSONDecodeError:
                # A torn read would itself be a finding, so record it as one
                # rather than swallowing it.
                self.observations.append((raw, {"__torn__": True}))
        else:
            self.observations.append(("", {}))
        return super().embed(texts)

    def written_during_this_run(self, before: str) -> list[dict]:
        """Observations that differ from the manifest as it stood at start."""
        return [
            parsed for raw, parsed in self.observations
            if raw != before and _entries(parsed)
        ]


def _project(root: Path, n_files: int = 6) -> Path:
    """A project whose files are big enough to produce real chunks.

    The imports are load bearing: without them extract_edges finds nothing and
    the graph tests below pass against an empty graph, proving nothing.
    """
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
    """indexing pinned at temp dirs so nothing touches the real databases."""
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    project = _project(tmp_path / "proj")
    paths = indexing._project_paths(str(project))
    return project, paths


@pytest.fixture
def unlocked(monkeypatch):
    """The index lock is one global file, not one per project.

    A real reindex running on this machine therefore makes every sweep test
    skip its work and pass vacuously. Caught exactly that way: these tests went
    green against "Index lock held by PID 26468 (reindex-batch)". Stubbing it
    keeps the suite independent of whatever the machine happens to be doing.
    """
    monkeypatch.setattr(ar, "acquire_index_lock", lambda *a, **k: True)
    monkeypatch.setattr(ar, "release_index_lock", lambda *a, **k: None)


def _entries(raw: dict) -> set[str]:
    return {k for k in raw if not k.startswith("__")}


def _edges_for(graph_db: Path, rel_path: str) -> int:
    """Edge count for one source file, read straight out of sqlite.

    Queried directly rather than through SQLiteGraphStore because the store
    exposes no per file read, and asserting on count_edges() alone could not
    tell "the right edges went" from "everything went".
    """
    import sqlite3

    conn = sqlite3.connect(str(graph_db))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM edges WHERE source_file = ?", (rel_path,)
        ).fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Defect A: the manifest must reach disk before the run ends
# ---------------------------------------------------------------------------

class TestCheckpointing:
    def test_the_manifest_is_written_before_the_run_finishes(self, rig, monkeypatch):
        """The whole defect in one assertion.

        Before the fix every observation was empty, because nothing was written
        until the final save. A hard kill at any point therefore lost the lot.
        """
        project, (_root, _pid, _idx, _chroma, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        watcher = WatchingEmbedder(manifest_path)

        indexing.index_project(str(project), watcher, force=True)

        assert watcher.observations, "the embedder was never called"
        assert watcher.written_during_this_run(before=""), (
            "no manifest entry ever reached disk while the run was in flight; "
            "a hard kill would have lost every file indexed so far"
        )

    def test_no_checkpoint_ever_names_a_file_whose_chunks_are_absent(
        self, rig, monkeypatch
    ):
        """The invariant that makes the fix safe rather than harmful.

        Writing the manifest before add_chunks commits would leave a permanent
        lie behind a crash. Nothing downstream compares the manifest against
        store contents, so such a file is never noticed and never reindexed.
        """
        project, (_root, _pid, _idx, chroma_dir, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        watcher = WatchingEmbedder(manifest_path)

        indexing.index_project(str(project), watcher, force=True)

        claimed: set[str] = set()
        for _raw, observation in watcher.observations:
            assert "__torn__" not in observation, "a checkpoint was read torn"
            claimed |= {
                k for k, v in observation.items()
                if not k.startswith("__") and v != indexing.UNREADABLE_SENTINEL
            }

        assert claimed, "nothing was checkpointed, so this proves nothing"

        store = ChromaStore(persist_dir=str(chroma_dir))
        for rel in sorted(claimed):
            assert store.get_by_source(COLLECTION, rel, limit=1), (
                f"a checkpoint claimed {rel} was indexed but no chunk for it "
                f"exists in the store: the manifest was written before the "
                f"chunks committed"
            )

    def test_a_file_whose_storage_failed_is_never_checkpointed(self, rig, monkeypatch):
        """The ordering test with teeth.

        When every file succeeds, the manifest and the store agree whichever
        order they are written in, so the test above would pass even with the
        manifest written first. One file has to fail to separate them.

        It has to fail AT add_chunks specifically, not earlier. A first attempt
        raised from the embedder instead and the mutant survived: embed() runs
        before the manifest line in both orderings, so neither one reached it
        and the test could not tell them apart. Storage is the step the manifest
        is making a claim about, so storage is the step that has to break.
        """
        project, (_root, _pid, _idx, chroma_dir, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        doomed = "module_03.py"

        real_add = ChromaStore.add_chunks

        def exploding_add(self, collection, chunks):
            if chunks and chunks[0].metadata.get("source_file") == doomed:
                raise RuntimeError("storage exploded")
            return real_add(self, collection, chunks)

        monkeypatch.setattr(ChromaStore, "add_chunks", exploding_add)

        watcher = WatchingEmbedder(manifest_path)
        result = indexing.index_project(str(project), watcher, force=True)

        assert result["files_failed"] == 1, (
            f"the sabotage did not land: {result}"
        )

        store = ChromaStore(persist_dir=str(chroma_dir))
        assert not store.get_by_source(COLLECTION, doomed, limit=1), (
            "the doomed file somehow stored chunks"
        )

        for _raw, observation in watcher.observations:
            assert doomed not in observation, (
                f"a checkpoint claimed {doomed} was indexed while its chunks "
                f"never reached the store: the manifest is being written "
                f"before the data it describes"
            )
        final = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert doomed not in final

    def test_every_mid_run_checkpoint_is_marked_incomplete(self, rig, monkeypatch):
        """_save_project_manifest carries over __ keys when passed None, so a
        checkpoint that omits incomplete keeps whatever the previous run left.

        A project whose last run finished cleanly would then keep claiming it
        was complete for the whole of this one, and index_is_incomplete would
        tell the next sweep to rebuild instead of resume.
        """
        project, (_root, _pid, _idx, _chroma, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)

        # First run completes cleanly, so __incomplete__ lands as False. That
        # stale False is exactly what a None would carry forward.
        indexing.index_project(str(project), StubEmbedder(), force=True)
        before = manifest_path.read_text(encoding="utf-8")
        assert json.loads(before)["__incomplete__"] is False

        watcher = WatchingEmbedder(manifest_path)
        indexing.index_project(str(project), watcher, force=True)

        # Anchored to `before`, because the first observation of this run is
        # the previous run's finished manifest still sitting on disk. Counting
        # that as a checkpoint is how this test passed while asserting nothing.
        mid_run = watcher.written_during_this_run(before)
        assert mid_run, "no mid run checkpoint to inspect"
        for observation in mid_run:
            assert observation.get("__incomplete__") is True, (
                "a mid run checkpoint did not mark the index incomplete, so a "
                "hard kill would leave a partial index claiming to be whole"
            )

    def test_a_clean_run_still_clears_incomplete_at_the_end(self, rig, monkeypatch):
        """The other half. If checkpointing left it stuck on True, every future
        sweep would treat a finished project as needing a resume."""
        project, (_root, _pid, _idx, _chroma, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)

        indexing.index_project(str(project), StubEmbedder(), force=True)

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert raw["__incomplete__"] is False
        assert indexing.index_is_incomplete(str(project)) is False

    def test_a_huge_interval_suppresses_mid_run_writes(self, rig, monkeypatch):
        """The constant has to mean something, or every file pays a full
        manifest write (~1.2MB on a 16k file project, multi gigabyte a run)."""
        project, (_root, _pid, _idx, _chroma, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 86_400.0)
        watcher = WatchingEmbedder(manifest_path)

        indexing.index_project(str(project), watcher, force=True)

        assert not watcher.written_during_this_run(before=""), (
            "a checkpoint fired despite a one day interval"
        )
        # The end of run save is unconditional and must still have happened.
        assert _entries(json.loads(manifest_path.read_text(encoding="utf-8")))

    def test_successive_checkpoints_are_at_least_an_interval_apart(
        self, rig, monkeypatch
    ):
        """The throttle itself, which the test above cannot see.

        With a one day interval the reset line never runs, so a mutant that
        drops the interval from it survives untouched. Proven: it did. This
        drives a deterministic clock instead and asserts the real property,
        that two checkpoints are never closer together than the interval.
        """
        project, (_root, _pid, _idx, _chroma, _manifest) = rig
        clock = _FakeClock(step=1.0)
        interval = 3.0
        monkeypatch.setattr(indexing, "time", clock)
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", interval)

        fired_at: list[float] = []
        real_save = indexing._save_project_manifest

        def spy(*args, **kwargs):
            if kwargs.get("incomplete") is True:
                fired_at.append(clock.now)
            return real_save(*args, **kwargs)

        monkeypatch.setattr(indexing, "_save_project_manifest", spy)
        indexing.index_project(str(project), StubEmbedder(), force=True)

        assert len(fired_at) >= 2, (
            f"need at least two checkpoints to measure a gap, got {fired_at}"
        )
        gaps = [b - a for a, b in zip(fired_at, fired_at[1:])]
        assert all(g >= interval for g in gaps), (
            f"checkpoints fired {gaps} apart against a {interval} interval, so "
            f"the interval is not throttling anything"
        )

    def test_checkpoint_failure_does_not_kill_the_run(self, rig, monkeypatch):
        """A transient manifest write error must not throw away hours of work,
        and must not be miscounted as an embedding failure either."""
        project, (_root, _pid, _idx, _chroma, _manifest) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)

        real_save = indexing._save_project_manifest
        calls = {"n": 0}

        def flaky(*args, **kwargs):
            calls["n"] += 1
            if kwargs.get("incomplete") is True:
                raise OSError("disk went away")
            return real_save(*args, **kwargs)

        monkeypatch.setattr(indexing, "_save_project_manifest", flaky)

        result = indexing.index_project(str(project), StubEmbedder(), force=True)

        assert calls["n"] > 1, "the checkpoint never fired, so nothing was proven"
        assert result.get("files_indexed", 0) > 0
        assert result.get("files_failed", 0) == 0, (
            "a manifest write error was counted against embedding, which "
            "reports a file whose chunks are safely stored as failed"
        )


# ---------------------------------------------------------------------------
# Defect B: a deleted file is dropped, not rebuilt around
# ---------------------------------------------------------------------------

class TestDeletedFileHandling:
    def _indexed(self, project, monkeypatch):
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        indexing.index_project(str(project), StubEmbedder(), force=True)

    def test_a_vanished_file_is_dropped_rather_than_erroring(self, rig, monkeypatch):
        """It used to return {"error": "File not found"} and bail, which is the
        whole reason a deletion escalated to a project wide rebuild."""
        project, (_root, _pid, _idx, _chroma, _manifest) = rig
        self._indexed(project, monkeypatch)
        victim = project / "module_00.py"
        victim.unlink()

        result = indexing.reindex_file(str(project), str(victim), StubEmbedder())

        assert result.get("deleted") is True, f"expected a deletion, got {result}"
        assert "error" not in result

    def test_its_chunks_leave_the_store(self, rig, monkeypatch):
        project, (_root, _pid, _idx, chroma_dir, _manifest) = rig
        self._indexed(project, monkeypatch)
        victim = project / "module_00.py"

        store = ChromaStore(persist_dir=str(chroma_dir))
        assert store.get_by_source(COLLECTION, "module_00.py", limit=1), (
            "the file was never indexed, so its removal proves nothing"
        )

        victim.unlink()
        indexing.reindex_file(str(project), str(victim), StubEmbedder())

        assert not ChromaStore(
            persist_dir=str(chroma_dir)
        ).get_by_source(COLLECTION, "module_00.py", limit=1), (
            "chunks for a deleted file are still searchable"
        )

    def test_its_manifest_entry_leaves_too(self, rig, monkeypatch):
        """Not blanked, dropped. find_changed_files only reports a path as
        deleted while the manifest still lists it, so a leftover entry hands
        the same dead file back on every sweep forever."""
        project, (_root, _pid, _idx, _chroma, manifest_path) = rig
        self._indexed(project, monkeypatch)
        victim = project / "module_00.py"
        victim.unlink()

        indexing.reindex_file(str(project), str(victim), StubEmbedder())

        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "module_00.py" not in raw

        _changed, deleted = ar.find_changed_files(str(project))
        assert "module_00.py" not in deleted, (
            "the file is still reported deleted after being dropped, so every "
            "future sweep would process it again"
        )

    def test_its_graph_edges_go_too(self, rig, monkeypatch):
        """Chunks and edges live in different databases, so removing one says
        nothing about the other. An orphaned edge outlives the file forever:
        there is no file left to reindex and nothing else clears it."""
        project, (_root, _pid, index_dir, _chroma, _manifest) = rig
        self._indexed(project, monkeypatch)
        victim = project / "module_00.py"

        graph_db = index_dir / "graph.db"
        assert graph_db.exists(), "no graph was built, so this proves nothing"
        assert _edges_for(graph_db, "module_00.py"), (
            "the file had no edges to begin with; the import header in "
            "_project is what makes this test meaningful"
        )

        victim.unlink()
        indexing.reindex_file(str(project), str(victim), StubEmbedder())

        assert _edges_for(graph_db, "module_00.py") == 0, (
            "graph edges for a deleted file survived, so graph search can "
            "still traverse into a file that no longer exists"
        )

    def test_other_files_keep_their_edges(self, rig, monkeypatch):
        """The obvious way to pass the test above is to delete too much."""
        project, (_root, _pid, index_dir, _chroma, _manifest) = rig
        self._indexed(project, monkeypatch)
        graph_db = index_dir / "graph.db"
        before = _edges_for(graph_db, "module_01.py")
        assert before

        (project / "module_00.py").unlink()
        indexing.reindex_file(
            str(project), str(project / "module_00.py"), StubEmbedder()
        )

        assert _edges_for(graph_db, "module_01.py") == before

    def test_other_files_are_left_alone(self, rig, monkeypatch):
        """The point of the fix. Deleting one file must not disturb the rest,
        which is exactly what the old force rebuild did."""
        project, (_root, _pid, _idx, chroma_dir, manifest_path) = rig
        self._indexed(project, monkeypatch)
        before = json.loads(manifest_path.read_text(encoding="utf-8"))

        victim = project / "module_00.py"
        victim.unlink()
        indexing.reindex_file(str(project), str(victim), StubEmbedder())

        after = json.loads(manifest_path.read_text(encoding="utf-8"))
        survivors = _entries(before) - {"module_00.py"}
        assert _entries(after) == survivors
        for rel in survivors:
            assert after[rel] == before[rel], f"{rel} was rehashed"

        store = ChromaStore(persist_dir=str(chroma_dir))
        for rel in survivors:
            assert store.get_by_source(COLLECTION, rel, limit=1), (
                f"{rel} lost its chunks when an unrelated file was deleted"
            )


class TestSweepDoesNotRebuildOnDeletion:
    def test_a_deletion_alone_never_calls_index_project(self, rig, unlocked, monkeypatch):
        """auto_reindex used to force=True the entire project the moment one
        file vanished. On the largest registered project that is hours of
        re embedding to remove a handful of rows."""
        project, (_root, _pid, _idx, _chroma, _manifest) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        indexing.index_project(str(project), StubEmbedder(), force=True)
        (project / "module_00.py").unlink()

        rebuilds = []
        monkeypatch.setattr(
            ar, "index_project",
            lambda *a, **k: rebuilds.append(k) or {"files_indexed": 0},
        )

        entry = {"project_path": str(project)}
        asyncio.run(ar._sweep_project("pid", entry, StubEmbedder()))

        assert rebuilds == [], (
            "a single deleted file still triggered a whole project rebuild"
        )

    def test_the_sweep_actually_removes_it(self, rig, unlocked, monkeypatch):
        """Not rebuilding is only correct if the deletion really is handled."""
        project, (_root, _pid, _idx, chroma_dir, _manifest) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        indexing.index_project(str(project), StubEmbedder(), force=True)
        (project / "module_00.py").unlink()

        asyncio.run(
            ar._sweep_project("pid", {"project_path": str(project)}, StubEmbedder())
        )

        assert not ChromaStore(
            persist_dir=str(chroma_dir)
        ).get_by_source(COLLECTION, "module_00.py", limit=1)

    def test_a_deletion_that_failed_blocks_a_resume(self, rig, unlocked, monkeypatch):
        """The one thing the old force-on-any-deletion rule got right.

        Resuming keeps the existing collection. That is correct when every
        deletion was actually dropped, and wrong when one was not: those stale
        chunks are only clearable by the wipe a force rebuild does. So a failed
        drop has to fall back to force even though the index is resumable.

        Without this the code reads perfectly and loses data quietly, which is
        why it gets its own test rather than riding along with the one below.
        """
        project, (_root, _pid, _idx, _chroma, manifest_path) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        indexing.index_project(str(project), StubEmbedder(), force=True)

        # An index that stopped early, so resuming is otherwise on the table.
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw["__incomplete__"] = True
        manifest_path.write_text(json.dumps(raw), encoding="utf-8")
        assert indexing.index_is_incomplete(str(project)) is True

        (project / "module_00.py").unlink()
        for f in range(1, 5):
            path = project / f"module_{f:02d}.py"
            path.write_text(path.read_text(encoding="utf-8") + "\nx = 1\n", encoding="utf-8")
        monkeypatch.setattr(ar, "FULL_REINDEX_THRESHOLD", 2)

        # The drop fails, the way a locked or unreadable database would fail it.
        # Patched on drop_manifest_key, which is what the sweep's deletion loop
        # calls. It used to route deletions through reindex_file with a flag;
        # eviction is its own function now, so patching reindex_file here would
        # intercept nothing, the real drop would succeed, and this test would
        # pass for the wrong reason.
        monkeypatch.setattr(
            ar, "drop_manifest_key", lambda *a, **k: {"error": "could not drop"}
        )

        forced = []

        def fake_index(project_path, cache, force=False, should_abort=None):
            forced.append(force)
            return {"files_indexed": 0, "chunks_created": 0, "files_failed": 0}

        monkeypatch.setattr(ar, "index_project", fake_index)
        asyncio.run(
            ar._sweep_project("pid", {"project_path": str(project)}, StubEmbedder())
        )

        assert forced == [True], (
            f"a deletion that was never dropped still allowed a resume "
            f"(force={forced}), leaving its chunks searchable forever"
        )

    def test_a_bulk_change_still_rebuilds(self, rig, unlocked, monkeypatch):
        """The threshold branch must survive the change. Deletions were pulled
        out of the forcing condition, the 50 file rule was not."""
        project, (_root, _pid, _idx, _chroma, _manifest) = rig
        monkeypatch.setattr(indexing, "INDEX_MANIFEST_CHECKPOINT_S", 0.0)
        indexing.index_project(str(project), StubEmbedder(), force=True)

        monkeypatch.setattr(ar, "FULL_REINDEX_THRESHOLD", 2)
        for f in range(4):
            path = project / f"module_{f:02d}.py"
            path.write_text(path.read_text(encoding="utf-8") + "\nx = 1\n", encoding="utf-8")

        rebuilds = []

        def fake_index(project_path, cache, force=False, should_abort=None):
            rebuilds.append(force)
            return {"files_indexed": 0, "chunks_created": 0, "files_failed": 0}

        monkeypatch.setattr(ar, "index_project", fake_index)
        asyncio.run(
            ar._sweep_project("pid", {"project_path": str(project)}, StubEmbedder())
        )

        assert rebuilds, "a change set over the threshold did not rebuild"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
