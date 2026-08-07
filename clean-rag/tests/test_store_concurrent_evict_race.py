"""Closing a cached ChromaStore connection must never happen under a live user.

The production incident: a background sweep called ChromaStore.evict_cache(),
which closed the process wide cached sqlite connection, while a different caller
still held the same handle. A caller between statements died with
sqlite3.ProgrammingError: Cannot operate on a closed database, and a caller mid
execute() did worse than raise, it took the whole process down with a Windows
access violation, which no except block can catch.

The gate in auto_reindex.py only covers one ordering, the sweep evicting a
project while its own _sweep_project call for that project is still running.
server/search.py builds its own ChromaStore per request and takes no index lock
at all, so the fix has to live in the connection cache itself: eviction marks the
record and the last holder to check in performs the close.

These tests run against the real server.store.ChromaStore, no mocks. The race
itself runs in a throwaway subprocess because the failure it guards against is a
process crash, not an exception, and killing the pytest process would be a worse
outcome than the bug.
"""
import hashlib
import math
import sqlite3
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server.store import ChromaStore, Chunk, _conn_cache  # noqa: E402


def _seed_store(persist_dir: Path, n_chunks: int = 200) -> None:
    with ChromaStore(persist_dir=str(persist_dir)) as store:
        store.create_collection("codebase")
        store.add_chunks("codebase", [
            Chunk(
                id=f"c{i}", content=f"content number {i}" * 20,
                embedding=[0.1, 0.2, 0.3, 0.4], metadata={"source_file": f"f{i}.py"},
            )
            for i in range(n_chunks)
        ])
    ChromaStore.evict_cache(str(persist_dir))


# list_sources() is the read used below because it does not catch anything: a
# closed handle surfaces as the real sqlite3.ProgrammingError instead of the
# empty list count() and search() would return.
_RACE_SCRIPT = textwrap.dedent(
    """
    import sys, threading, time
    sys.path.insert(0, {clean_rag!r})
    from server.store import ChromaStore

    persist_dir = {persist_dir!r}
    reader_store = ChromaStore(persist_dir=persist_dir)
    # The raw handle, kept so the deferred close can be observed after the last
    # holder checks in. There is no public way to ask a sqlite3.Connection
    # whether it is closed, and whether the OS handle actually went away is
    # exactly what is being asserted.
    raw_conn = reader_store._conn

    started = threading.Event()
    error = {{}}

    def slow_reader():
        try:
            started.set()
            for _ in range(5000):
                reader_store.list_sources("codebase")
        except Exception as e:
            error["error"] = repr(e)

    t = threading.Thread(target=slow_reader)
    t.start()
    started.wait(timeout=2)
    time.sleep(0.005)
    ChromaStore.evict_cache(persist_dir)
    t.join(timeout=30)
    print("ERROR:" + error.get("error", "NONE"))

    # The evicted handle stays usable for the holder that still has it.
    try:
        reader_store.list_sources("codebase")
        print("USABLE_AFTER_EVICT:True")
    except Exception as e:
        print("USABLE_AFTER_EVICT:" + repr(e))

    # And the deferred close really happens once that holder releases it,
    # otherwise the eviction leaked a connection instead of freeing one.
    reader_store.close()
    try:
        raw_conn.execute("SELECT 1")
        print("CLOSED_AFTER_RELEASE:False")
    except Exception as e:
        print("CLOSED_AFTER_RELEASE:" + type(e).__name__)
    """
)


def test_evict_cache_during_a_live_query_leaves_the_reader_working(tmp_path):
    """One thread holds a ChromaStore and loops a read (a live /search), the
    other calls evict_cache for the same persist_dir (the sweep's
    _release_project_resources) while the first is still running.

    Before the connection cache deferred its closes, this crashed the
    interpreter with a Windows access violation four runs in five and raised
    "Cannot operate on a closed database" on the fifth. Both outcomes are
    asserted against here: a clean exit, and no error on the reader.
    """
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir(parents=True)
    _seed_store(persist_dir, n_chunks=500)

    script = _RACE_SCRIPT.format(clean_rag=str(CLEAN_RAG), persist_dir=str(persist_dir))
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, timeout=120,
    )

    assert proc.returncode == 0, (
        f"the subprocess did not exit cleanly, which is how the unguarded close "
        f"showed up (0xC0000005 access violation inside conn.close()): "
        f"returncode={proc.returncode}, stdout={proc.stdout!r}, "
        f"stderr={proc.stderr[-2000:]!r}"
    )
    assert "ERROR:NONE" in proc.stdout, (
        f"the reader was interrupted by the concurrent evict: "
        f"stdout={proc.stdout!r} stderr={proc.stderr[-2000:]!r}"
    )
    assert "USABLE_AFTER_EVICT:True" in proc.stdout, (
        f"the evicted handle stopped working for the holder that still had it: "
        f"stdout={proc.stdout!r}"
    )
    assert "CLOSED_AFTER_RELEASE:ProgrammingError" in proc.stdout, (
        f"the deferred close never ran once the last holder released the "
        f"handle, so the eviction leaked the connection it was meant to free: "
        f"stdout={proc.stdout!r}"
    )


def test_evicting_a_held_connection_defers_the_close_until_the_holder_releases(tmp_path):
    """The contract behind the race, asserted without threads.

    A holder keeps working after its connection is evicted, a store opened
    during the deferral joins that same handle instead of opening a second one,
    and the handle is closed the moment the last of them checks in. The close, not
    the removal from the cache, is what makes the eviction real: a marked record
    is one that goes away at the first moment nothing is using it.
    """
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir(parents=True)
    _seed_store(persist_dir, n_chunks=5)

    holder = ChromaStore(persist_dir=str(persist_dir))
    evicted_conn = holder._conn

    ChromaStore.evict_cache(str(persist_dir))

    assert len(holder.list_sources("codebase")) == 5, (
        "evict_cache closed a handle a live holder was still using"
    )

    fresh = ChromaStore(persist_dir=str(persist_dir))
    assert fresh._conn is evicted_conn, (
        "a store opened during the deferral got a SECOND connection to a file "
        "the first store still has open"
    )
    assert fresh._write_lock is holder._write_lock, (
        "two live stores on one db file got two different write locks, so "
        "neither one serializes the other's writes"
    )
    fresh.close()

    assert len(holder.list_sources("codebase")) == 5, (
        "the second store's close took the handle away from the holder that "
        "still had it"
    )

    holder.close()
    with pytest.raises(sqlite3.ProgrammingError):
        evicted_conn.execute("SELECT 1")


def test_evict_closes_immediately_when_no_one_holds_the_connection(tmp_path):
    """The sweep's normal case must stay prompt: with no live holder there is
    nothing to defer to, and the handle has to go now, or the memory hygiene
    the sweep exists for is lost.
    """
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir(parents=True)
    _seed_store(persist_dir, n_chunks=5)

    store = ChromaStore(persist_dir=str(persist_dir))
    conn = store._conn
    store.close()

    ChromaStore.evict_cache(str(persist_dir))

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


class _EvictingEmbedder:
    """Fires the sweep's own release on its first embed call.

    Signed hashed bag of words, the same shape the other suites use, so the
    values are deterministic and no model is loaded. What it adds is the timing
    of the incident: the eviction lands while index_project still holds its
    store, between two of its statements.
    """

    model_name = "stub-embedder"
    _DIM = 64

    def __init__(self, on_first_embed):
        self._on_first_embed = on_first_embed
        self.embeds = 0

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self._DIM
        for tok in text.lower().split():
            h = int(hashlib.sha256(tok.encode("utf-8")).hexdigest(), 16)
            v[h % self._DIM] += 1.0 if (h // self._DIM) % 2 == 0 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, texts):
        self.embeds += 1
        if self.embeds == 1:
            self._on_first_embed()
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def test_a_sweep_release_mid_index_does_not_kill_the_run(tmp_path, monkeypatch):
    """The production incident, end to end, through the real functions.

    A /index-project run of a large project outlives one sweep interval, so the
    sweep called release_project_resources for a project the run was still
    indexing. The run then died at its next write:

        indexing.py:658  store.delete_by_source(collection, rel_path)
        store.py:336     rows = self._conn.execute(...)
        sqlite3.ProgrammingError: Cannot operate on a closed database.

    Every project too big to index in one interval was therefore permanently
    __incomplete__. The gate in auto_reindex.py stops the sweep from asking, and
    this asserts the store survives being asked anyway, which is what covers
    every other caller of the eviction.
    """
    from server import config as config_mod
    from server import indexing
    from server.reindex_unit import release_project_resources

    databases_dir = tmp_path / "databases"
    monkeypatch.setattr(indexing, "DATABASES_DIR", databases_dir)
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config_mod, "DATABASES_DIR", databases_dir)

    project = tmp_path / "proj"
    project.mkdir()
    n_files = 4
    for f in range(n_files):
        (project / f"module_{f:02d}.py").write_text(
            "import os\nimport json\n" + "\n".join(
                f"def handler_{f}_{i}(payload):\n"
                f'    """Normalise one payload."""\n'
                f"    return {{'total': sum(payload), 'n': {i}}}\n"
                for i in range(4)
            ),
            encoding="utf-8",
        )

    pid = indexing._project_paths(str(project))[1]
    embedder = _EvictingEmbedder(lambda: release_project_resources(pid))

    result = indexing.index_project(str(project), embedder, force=True)

    assert embedder.embeds >= 1, "the embedder never ran, so nothing was evicted"
    assert result.get("files_indexed") == n_files, (
        f"the index run did not finish after the sweep released its "
        f"connection: {result}"
    )
    assert not result.get("files_failed"), (
        f"files failed after the mid run eviction: {result}"
    )


def test_a_store_opened_during_a_deferred_close_shares_the_one_write_lock(tmp_path):
    """Two stores on one db file must never end up with two write locks.

    Eviction with a live holder leaves the OLD connection open, which is the
    deferral working as intended. The trap is the store opened next for the same
    persist_dir: if the eviction has already dropped the shared record, that
    store opens a SECOND connection with its OWN write_lock, and the two locks
    guard nothing across the pair.

    _ensure_vec_table is a check then create and its own docstring requires
    self._write_lock "to avoid a check-then-create race between threads", which
    assumes exactly one lock per db file. With two, both writers checked, both
    found no vec table, and both issued CREATE VIRTUAL TABLE (vec0 has no
    IF NOT EXISTS): the loser's whole add_chunks raised
    OperationalError('table vec_codebase already exists') and none of its 50
    chunks were written. The barrier below is what makes that interleave
    deterministic rather than occasional.
    """
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir(parents=True)
    with ChromaStore(persist_dir=str(persist_dir)) as s:
        s.create_collection("codebase")
    ChromaStore.evict_cache(str(persist_dir))

    holder = ChromaStore(persist_dir=str(persist_dir))  # the lingering old writer
    ChromaStore.evict_cache(str(persist_dir))           # defers holder's close
    fresh = ChromaStore(persist_dir=str(persist_dir))   # opened during the deferral

    assert fresh._conn is holder._conn, (
        "two live connections to one db file: the deferred close let a second "
        "one be opened beside the first"
    )
    assert fresh._write_lock is holder._write_lock, (
        "one db file, two write locks: neither writer serializes the other"
    )

    errors = {}
    barrier = threading.Barrier(2)
    per_writer = 50

    def writer(store, label):
        try:
            barrier.wait(timeout=5)
            store.add_chunks("codebase", [
                Chunk(
                    id=f"{label}-{i}", content=f"payload {label} {i}",
                    embedding=[0.1, 0.2, 0.3, 0.4],
                    metadata={"source_file": f"{label}{i}.py"},
                )
                for i in range(per_writer)
            ])
        except Exception as e:
            errors[label] = repr(e)

    tA = threading.Thread(target=writer, args=(holder, "A"))
    tB = threading.Thread(target=writer, args=(fresh, "B"))
    tA.start()
    tB.start()
    tA.join(timeout=30)
    tB.join(timeout=30)

    assert not errors, (
        "a second, independently locked connection to the same db file let two "
        "writers race _ensure_vec_table's check-then-create, so one writer's "
        f"whole add_chunks call raised and its rows were silently never "
        f"written: {errors}"
    )
    assert holder.count("codebase") == per_writer * 2, (
        "both writers reported success but the rows are not all there"
    )

    holder.close()
    fresh.close()


def _indexed_project(tmp_path, monkeypatch, n_chunks: int = 5):
    """A project search.py can actually resolve, with a real seeded index.

    Returns (project_path, pid, chroma_dir). Both DATABASES_DIR copies are
    repointed: search.py reads its own module level import, and
    release_project_resources reads config's at call time.
    """
    from server import config as config_mod
    from server import search as search_mod
    from server.project_id import project_dir_name

    project = tmp_path / "proj"
    project.mkdir()
    databases_dir = tmp_path / "databases"
    pid = project_dir_name(str(project))
    chroma_dir = databases_dir / "_projects" / pid / "chroma"
    chroma_dir.mkdir(parents=True)
    _seed_store(chroma_dir, n_chunks=n_chunks)

    monkeypatch.setattr(search_mod, "DATABASES_DIR", databases_dir)
    monkeypatch.setattr(config_mod, "DATABASES_DIR", databases_dir)
    return project, pid, chroma_dir


class _StubEmbedder:
    """Returns the vector _seed_store used, so every chunk scores 1.0.

    on_query fires from inside embed_query, which is called after
    _search_project has already opened its store and before it has finished
    with it. That is where a sweep lands in production, and it is the only
    moment worth testing.
    """

    def __init__(self, on_query=None):
        self._on_query = on_query

    def embed_query(self, text):
        if self._on_query is not None:
            self._on_query()
        return [0.1, 0.2, 0.3, 0.4]


def test_a_sweep_release_mid_search_does_not_break_the_search(tmp_path, monkeypatch):
    """search.py's own entry point against the sweep's own release call.

    _search_project opens a ChromaStore per request and takes no index lock, so
    nothing in auto_reindex protects it. The eviction below is the real
    release_project_resources the sweep runs, fired while this search holds the
    handle, and the search still has to return its rows.
    """
    from server import search as search_mod
    from server.reindex_unit import release_project_resources

    project, pid, chroma_dir = _indexed_project(tmp_path, monkeypatch)

    probe = ChromaStore(persist_dir=str(chroma_dir))
    db_path, conn = probe._db_path, probe._conn
    probe.close()

    results = search_mod._search_project(
        "content number", str(project),
        _StubEmbedder(on_query=lambda: release_project_resources(pid)),
        limit=5, min_score=0.0,
    )

    assert len(results) == 5, (
        f"the sweep's release closed the handle under a live search: {results}"
    )
    assert db_path not in _conn_cache, (
        "the eviction never took effect: the record is still being served after "
        "the last holder left"
    )
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_search_project_checks_its_connection_in_even_when_it_raises(tmp_path, monkeypatch):
    """A raised search must not pin the connection to the traceback.

    _search_project used to leave the check in to garbage collection. Anything
    holding the exception (an error reporter, a retry queue, pytest's own
    ExceptionInfo below) also holds the frame it was raised from, and so the
    store local in that frame, so a connection the sweep asked to close stayed
    open for as long as that reference lived. Bound with `as raised` on purpose:
    the exception is deliberately still alive at the assertions.
    """
    from server import search as search_mod
    from server.reindex_unit import release_project_resources

    project, pid, chroma_dir = _indexed_project(tmp_path, monkeypatch)

    probe = ChromaStore(persist_dir=str(chroma_dir))
    db_path, conn = probe._db_path, probe._conn
    probe.close()

    def evict_then_fail():
        release_project_resources(pid)
        raise RuntimeError("embedding model fell over mid search")

    with pytest.raises(RuntimeError) as raised:
        search_mod._search_project(
            "content number", str(project), _StubEmbedder(on_query=evict_then_fail),
            limit=5, min_score=0.0,
        )

    assert "fell over" in str(raised.value)
    assert db_path not in _conn_cache, (
        "the failed search never checked its connection in, so the evicted "
        "record is still cached while the traceback is held"
    )
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_clear_cache_also_waits_for_a_live_holder(tmp_path):
    """Shutdown takes the same path. clear_cache() force closing everything
    would crash a worker thread that is still mid statement, and the process
    exit that follows releases the file anyway.
    """
    persist_dir = tmp_path / "chroma"
    persist_dir.mkdir(parents=True)
    _seed_store(persist_dir, n_chunks=5)

    holder = ChromaStore(persist_dir=str(persist_dir))
    conn = holder._conn

    ChromaStore.clear_cache()

    assert len(holder.list_sources("codebase")) == 5, (
        "clear_cache closed a handle a live holder was still using"
    )

    holder.close()
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")
