"""/status reports a cumulative file count, and the registry keeps one writer.

The reported bug: the console's State column read ``files_indexed``, which is
a per run counter. A project whose last sweep found nothing changed writes 0
and rendered EMPTY while holding 1,072 vectors, 1,486 edges and 223 nodes. The
same misreading was already caught once for the table headers, renamed to
"Run files" and "Run chunks" at console.py:356, and the State cell was missed.

Two rejected designs are pinned here as tests, because both look obviously
right and both are wrong.

Storing the total in state/projects.json and writing it from reindex_file and
drop_manifest_key. That puts a registry writer behind /reindex-file, and
``test_only_the_indexing_route_reaches_a_registry_writer`` refuses it: the
gate on /run-tests, /mutation-test and /security-scan reads presence in that
file as proof this server indexed the directory, so a second way to add an
entry makes the gate self service. Moving the write to the sweep timer got
past that walk and then failed two more source level checks, the last of
which forbids anything outside the indexing pipeline from even naming the
writer. ``test_the_registry_still_has_one_writer`` keeps that shut.

Writing the total from a partial call to ``_update_project_registry``. That
function built a fresh entry and assigned it, adding "graph" only when
graph_stats was truthy, so any caller that measured no graph erased the edge
and node counts. The merge fix stays even though the partial caller is gone,
and ``test_a_partial_write_keeps_the_graph_counts`` is what proves it.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app as app_mod  # noqa: E402
from server import auto_reindex  # noqa: E402
from server import indexing  # noqa: E402


@pytest.fixture
def state(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setattr(indexing, "STATE_DIR", d)
    return d


def _registry(state) -> dict:
    return json.loads((state / "projects.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The registry writer merges rather than replaces
# ---------------------------------------------------------------------------

def test_a_partial_write_keeps_the_graph_counts(state):
    indexing._update_project_registry(
        "pid1", "C:/proj", files_indexed=12, chunks_created=340,
        graph_stats={"edges_total": 1486, "pagerank_nodes": 223},
    )
    indexing._update_project_registry("pid1", "C:/proj", files_indexed=0)

    entry = _registry(state)["pid1"]
    assert entry["graph"] == {"edges_total": 1486, "pagerank_nodes": 223}


def test_a_partial_write_keeps_the_per_run_counters(state):
    indexing._update_project_registry(
        "pid1", "C:/proj", files_indexed=12, chunks_created=340)
    indexing._update_project_registry(
        "pid1", "C:/proj", graph_stats={"edges_total": 5})

    entry = _registry(state)["pid1"]
    assert entry["files_indexed"] == 12
    assert entry["chunks_created"] == 340


def test_a_full_write_still_overwrites_every_stat(state):
    """Merging must not turn a real reindex into an append only record."""
    indexing._update_project_registry(
        "pid1", "C:/proj", files_indexed=12, chunks_created=340,
        graph_stats={"edges_total": 1486},
    )
    indexing._update_project_registry(
        "pid1", "C:/proj", files_indexed=3, chunks_created=9,
        graph_stats={"edges_total": 2},
    )
    entry = _registry(state)["pid1"]
    assert entry["files_indexed"] == 3
    assert entry["chunks_created"] == 9
    assert entry["graph"] == {"edges_total": 2}


def test_a_second_project_is_untouched(state):
    indexing._update_project_registry("pid1", "C:/a", files_indexed=1)
    indexing._update_project_registry("pid2", "C:/b", files_indexed=2)
    reg = _registry(state)
    assert reg["pid1"]["files_indexed"] == 1
    assert reg["pid2"]["files_indexed"] == 2


def test_a_corrupt_prior_entry_does_not_crash_the_write(state):
    state.mkdir(parents=True)
    (state / "projects.json").write_text(
        json.dumps({"pid1": "not a dict"}), encoding="utf-8")
    indexing._update_project_registry("pid1", "C:/proj", files_indexed=7)
    assert _registry(state)["pid1"]["files_indexed"] == 7


def test_the_registry_still_has_one_writer():
    """The rejected design, pinned so it does not come back quietly.

    The three checks in test_exec_routes_require_registered_project.py are the
    real guard. This one names the specific function that was tried and
    removed, so the next person reading this file sees why /status computes
    the number instead of storing it.
    """
    assert not hasattr(indexing, "sync_files_total")
    src = (Path(indexing.__file__).parent / "auto_reindex.py").read_text(
        encoding="utf-8")
    assert "_update_project_registry" not in src


# ---------------------------------------------------------------------------
# What the count counts
# ---------------------------------------------------------------------------

def test_the_count_ignores_dunder_metadata_keys():
    manifest = {
        "__project_path__": "C:/proj",
        "__model_id__": "CodeRankEmbed",
        "__incomplete__": True,
        "a.py": "h1",
        "b/c.py": "h2",
    }
    assert indexing.manifest_file_count(manifest) == 2


def test_an_empty_manifest_counts_zero():
    assert indexing.manifest_file_count({"__project_path__": "C:/p"}) == 0


@pytest.mark.parametrize("key", [
    "__tests__/Foo.test.js",
    "__init__.py",
    "__main__.py",
    "__mocks__/api.js",
])
def test_a_file_whose_path_starts_with_two_underscores_is_a_file(key):
    """Not metadata. The two namespaces share one dict and only the writer's
    own names are reserved.

    __tests__/ is the Jest layout and 71 of those keys sit in the ContosoMobile
    manifest, the project whose row started this. A startswith("__") filter
    counted 304 of its 375 files.
    """
    assert indexing.manifest_file_count({key: "h1", "app.js": "h2"}) == 2


def test_the_metadata_keys_are_the_ones_the_writer_writes(tmp_path):
    """The reserved set has to stay the set _save_project_manifest emits.

    Drift either way is a silent miscount: a name it writes but the set omits
    inflates the total, and a name in the set it never writes is dead weight
    that a real file path could one day match.
    """
    p = tmp_path / "manifest.json"
    indexing._save_project_manifest(
        p, {}, "C:/proj",
        pipeline_version=3, model_id="CodeRankEmbed", embedding_dim=768,
        incomplete=True,
    )
    written = set(json.loads(p.read_text(encoding="utf-8")))
    assert written == set(indexing.MANIFEST_METADATA_KEYS)


@pytest.mark.parametrize("module", [indexing, auto_reindex])
def test_no_manifest_reader_is_left_on_the_prefix_filter(module):
    """Every site that splits metadata from file paths reads the reserved set.

    The count was only one of five places in indexing.py. Fixing the count
    alone left the loaders still dropping a __tests__ key, which erased it
    from the manifest on the next single file reindex and put the number
    straight back where it was.

    auto_reindex is checked too because it was the last holdout and the only
    one this test did not look at. Its copy of the filter made a deleted
    __tests__ file invisible to the sweep, so its key and its vectors were
    never evicted and the count it fed stayed permanently high.
    """
    src = Path(module.__file__).read_text(encoding="utf-8")
    assert 'startswith("__")' not in src


# ---------------------------------------------------------------------------
# /status computes it, reads it from cache, and never writes anything
# ---------------------------------------------------------------------------

def _seed_manifest(tmp_path, name, payload) -> Path:
    p = tmp_path / name / "manifest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def clear_cache():
    app_mod._FILES_TOTAL_CACHE.clear()
    yield
    app_mod._FILES_TOTAL_CACHE.clear()


def _route_manifests(monkeypatch, mapping):
    def fake(project_path):
        return (Path(project_path), "pid", Path("."), Path("."),
                mapping[project_path])
    monkeypatch.setattr(app_mod, "_project_paths", fake)


def test_status_reports_the_total_from_the_manifest(tmp_path, monkeypatch):
    m = _seed_manifest(tmp_path, "one", {
        "__project_path__": "C:/proj", "a.py": "h", "b.py": "h", "c.py": "h"})
    _route_manifests(monkeypatch, {"C:/proj": m})

    out = app_mod._with_files_total({
        "pid1": {"project_path": "C:/proj", "files_indexed": 0,
                 "graph": {"edges_total": 1486}},
    })
    assert out["pid1"]["files_total"] == 3
    assert out["pid1"]["graph"] == {"edges_total": 1486}
    assert out["pid1"]["files_indexed"] == 0


def test_the_stored_entry_is_not_mutated(tmp_path, monkeypatch):
    """A read path that edits the registry dict in place is a write by accident."""
    m = _seed_manifest(tmp_path, "one", {"a.py": "h"})
    _route_manifests(monkeypatch, {"C:/proj": m})

    stored = {"pid1": {"project_path": "C:/proj"}}
    app_mod._with_files_total(stored)
    assert "files_total" not in stored["pid1"]


def test_an_unreadable_manifest_reports_no_total(tmp_path, monkeypatch):
    """Absent, never 0. 0 claims the project was measured and found empty."""
    _route_manifests(monkeypatch, {"C:/gone": tmp_path / "nothing" / "manifest.json"})
    out = app_mod._with_files_total({"pid1": {"project_path": "C:/gone"}})
    assert "files_total" not in out["pid1"]


def test_a_corrupt_manifest_reports_no_total(tmp_path, monkeypatch):
    p = tmp_path / "bad" / "manifest.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    _route_manifests(monkeypatch, {"C:/proj": p})
    out = app_mod._with_files_total({"pid1": {"project_path": "C:/proj"}})
    assert "files_total" not in out["pid1"]


def test_a_manifest_that_is_not_an_object_reports_no_total(tmp_path, monkeypatch):
    p = tmp_path / "list" / "manifest.json"
    p.parent.mkdir(parents=True)
    p.write_text("[1, 2, 3]", encoding="utf-8")
    _route_manifests(monkeypatch, {"C:/proj": p})
    out = app_mod._with_files_total({"pid1": {"project_path": "C:/proj"}})
    assert "files_total" not in out["pid1"]


def test_an_entry_with_no_path_reports_no_total():
    out = app_mod._with_files_total({"pid1": {"files_indexed": 4}})
    assert "files_total" not in out["pid1"]


@pytest.mark.parametrize("path", [123, True, ["C:/proj"], {"a": 1}, 0, ""])
def test_a_project_path_that_is_not_a_string_reports_no_total(path):
    """Nothing validates state/projects.json on the way in.

    A truthy non string reached Path() and raised TypeError, and /status
    builds one response covering every project, so a single malformed entry
    answered 500 for all of them.
    """
    out = app_mod._with_files_total({"pid1": {"project_path": path,
                                              "files_indexed": 5}})
    assert "files_total" not in out["pid1"]
    assert out["pid1"]["files_indexed"] == 5


@pytest.mark.parametrize("registry", [[1, 2], "nope", 7, None, 3.14, True])
def test_a_registry_that_is_not_an_object_becomes_an_empty_one(registry):
    """A corrupt root is still not a reason to fail the whole request.

    This used to assert the argument came back unchanged, and passed while the
    bug it was written against stayed live: handle_status calls len() on the
    result, and 7, None, 3.14 and True have no __len__, so the passthrough fed
    the 500 it was supposed to prevent. Asserting the type the caller needs is
    what makes it bite.
    """
    assert app_mod._with_files_total(registry) == {}


def test_a_project_of_dunder_named_files_renders_indexed(tmp_path, monkeypatch,
                                                         state_of):
    """End to end on the shape that reported EMPTY while holding real files."""
    m = _seed_manifest(tmp_path, "rn", {
        "__project_path__": "C:/proj",
        "__tests__/Foo.test.js": "h1",
        "__tests__/Bar.test.js": "h2",
    })
    _route_manifests(monkeypatch, {"C:/proj": m})

    out = app_mod._with_files_total({
        "pid1": {"project_path": "C:/proj", "files_indexed": 0,
                 "chunks_created": 0},
    })
    assert out["pid1"]["files_total"] == 2
    assert str(state_of(out["pid1"], "")) == "INDEXED"


def test_a_non_dict_entry_passes_through():
    out = app_mod._with_files_total({"pid1": "not a dict"})
    assert out["pid1"] == "not a dict"


def test_the_second_read_comes_from_cache(tmp_path, monkeypatch):
    """One stat per project per tick, not a full parse. The console polls
    every 3 seconds and the largest manifest here holds 1,731 entries."""
    m = _seed_manifest(tmp_path, "one", {"a.py": "h", "b.py": "h"})
    _route_manifests(monkeypatch, {"C:/proj": m})
    entries = {"pid1": {"project_path": "C:/proj"}}

    assert app_mod._with_files_total(entries)["pid1"]["files_total"] == 2

    reads = []
    real = Path.read_text

    def counting(self, *a, **k):
        reads.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", counting)
    assert app_mod._with_files_total(entries)["pid1"]["files_total"] == 2
    assert reads == []


def test_a_changed_manifest_invalidates_the_cache(tmp_path, monkeypatch):
    m = _seed_manifest(tmp_path, "one", {"a.py": "h"})
    _route_manifests(monkeypatch, {"C:/proj": m})
    entries = {"pid1": {"project_path": "C:/proj"}}
    assert app_mod._with_files_total(entries)["pid1"]["files_total"] == 1

    import os
    m.write_text(json.dumps({"a.py": "h", "b.py": "h"}), encoding="utf-8")
    st = m.stat()
    os.utime(m, (st.st_atime, st.st_mtime + 10))

    assert app_mod._with_files_total(entries)["pid1"]["files_total"] == 2


def test_a_rewrite_under_the_same_mtime_still_invalidates(tmp_path, monkeypatch):
    """Two writes milliseconds apart can share an mtime: 2 of 20 did when
    measured on this machine. Size is the second half of the stamp."""
    import os
    m = _seed_manifest(tmp_path, "one", {"a.py": "h"})
    _route_manifests(monkeypatch, {"C:/proj": m})
    entries = {"pid1": {"project_path": "C:/proj"}}
    assert app_mod._with_files_total(entries)["pid1"]["files_total"] == 1

    frozen = m.stat()
    m.write_text(json.dumps({"a.py": "h", "b.py": "h"}), encoding="utf-8")
    os.utime(m, (frozen.st_atime, frozen.st_mtime))

    assert app_mod._with_files_total(entries)["pid1"]["files_total"] == 2


def test_reading_the_status_never_touches_the_registry(tmp_path, state, monkeypatch):
    m = _seed_manifest(tmp_path, "one", {"a.py": "h"})
    _route_manifests(monkeypatch, {"C:/proj": m})
    state.mkdir(parents=True)
    reg = state / "projects.json"
    reg.write_text(json.dumps({"pid1": {"project_path": "C:/proj"}}), encoding="utf-8")
    before = reg.read_bytes()

    app_mod._with_files_total(json.loads(before))
    assert reg.read_bytes() == before


# ---------------------------------------------------------------------------
# What the console renders
# ---------------------------------------------------------------------------

@pytest.fixture
def state_of():
    from cli.console import _state_of
    return _state_of


def test_the_reported_row_now_reads_indexed(state_of):
    """ContosoMobile: 0 files this run, 458 in the index, and it said EMPTY."""
    entry = {"project_path": "C:/proj", "files_indexed": 0, "chunks_created": 0,
             "files_total": 458,
             "graph": {"edges_total": 1486, "pagerank_nodes": 223}}
    assert str(state_of(entry, "")) == "INDEXED"


def test_a_genuinely_empty_project_still_reads_empty(state_of):
    entry = {"project_path": "C:/proj", "files_indexed": 0, "chunks_created": 0,
             "files_total": 0}
    assert str(state_of(entry, "")) == "EMPTY"


def test_indexing_wins_over_the_total(state_of):
    entry = {"project_path": "C:/proj", "files_total": 0}
    assert str(state_of(entry, "C:/proj")) == "INDEXING"


def test_an_unreadable_manifest_falls_back_to_the_graph(state_of):
    """files_total is absent when the manifest could not be read, so the cell
    uses whatever liveness signal the entry does carry rather than claiming
    the project is empty."""
    entry = {"project_path": "C:/proj", "files_indexed": 0, "chunks_created": 0,
             "graph": {"edges_total": 1486, "pagerank_nodes": 223}}
    assert str(state_of(entry, "")) == "INDEXED"


def test_the_fallback_accepts_chunks_with_no_graph(state_of):
    """Domain holds 10,566 vectors and zero edges, so graph alone is not enough."""
    entry = {"project_path": "C:/proj", "files_indexed": 0, "chunks_created": 900,
             "graph": {"edges_total": 0, "pagerank_nodes": 0}}
    assert str(state_of(entry, "")) == "INDEXED"


def test_the_fallback_says_empty_when_nothing_is_there(state_of):
    entry = {"project_path": "C:/proj", "files_indexed": 0, "chunks_created": 0}
    assert str(state_of(entry, "")) == "EMPTY"


# --------------------------------------------------------------------------
# The registry read boundary. state/projects.json is untrusted: nothing
# validates what its root or its entries are, and three callers rely on the
# dict that _list_projects promises.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["7", "null", "3.14", "true", '"nope"', "[1, 2]"])
def test_a_registry_root_that_is_not_an_object_reads_as_empty(root, tmp_path,
                                                              monkeypatch):
    """Every caller takes len(), .values() or json of this. None survive a scalar."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "projects.json").write_text(root, encoding="utf-8")
    monkeypatch.setattr(app_mod, "STATE_DIR", state_dir)

    assert app_mod._list_projects() == {}


def test_a_real_registry_still_reads_back(tmp_path, monkeypatch):
    """The guard above must not swallow a registry that is fine."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    entry = {"pid1": {"project_path": "C:/proj", "files_indexed": 5}}
    (state_dir / "projects.json").write_text(json.dumps(entry), encoding="utf-8")
    monkeypatch.setattr(app_mod, "STATE_DIR", state_dir)

    assert app_mod._list_projects() == entry


def test_the_exec_gate_refuses_past_a_non_object_entry(monkeypatch):
    """A malformed entry must not stop the walk reaching a real one, and must
    not grant anything itself. .get() on it used to raise out of the handler,
    so one bad entry answered 500 for every gated route."""
    monkeypatch.setattr(app_mod, "_list_projects", lambda: {"junk": 5})

    response = app_mod._registered_project_or_error("C:/proj", "runs tests")

    assert response is not None and response.status == 403


# --------------------------------------------------------------------------
# The manifest read boundary. Same shape as the registry: nothing validates
# what a manifest.json root is, and a sweep walks every project in one pass,
# so one bad root raising takes the projects behind it down too.
# --------------------------------------------------------------------------

@pytest.fixture
def scalar_manifest_project(tmp_path, monkeypatch, request):
    """A project whose manifest holds the parametrized non object root."""
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "real.js").write_text("console.log(1)", encoding="utf-8")
    manifest_path = indexing._project_paths(str(proj))[4]
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(request.param, encoding="utf-8")
    return str(proj)


_SCALAR_ROOTS = ["7", "null", "3.14", "true", '"nope"', "[1, 2]"]


@pytest.mark.parametrize("scalar_manifest_project", _SCALAR_ROOTS, indirect=True)
def test_the_sweep_survives_a_non_object_manifest(scalar_manifest_project):
    assert auto_reindex.find_changed_files(scalar_manifest_project) == ([], [])


@pytest.mark.parametrize("scalar_manifest_project", _SCALAR_ROOTS, indirect=True)
def test_incompleteness_survives_a_non_object_manifest(scalar_manifest_project):
    """False, not a raise. A resume decision cannot be read off this file."""
    assert indexing.index_is_incomplete(scalar_manifest_project) is False


@pytest.mark.parametrize("scalar_manifest_project", _SCALAR_ROOTS, indirect=True)
def test_provenance_survives_a_non_object_manifest(scalar_manifest_project):
    """Unknown, which search already treats as unsafe rather than a match."""
    assert indexing.read_project_provenance(scalar_manifest_project) == {
        "model_id": None, "embedding_dim": None,
    }


@pytest.mark.parametrize("root", ["7", "null", "3.14", "true", '"nope"', "[1, 2]"])
def test_the_registry_writer_survives_a_scalar_root(root, state):
    """index_project calls this last, after every file is embedded. .get() on a
    scalar raised there and lost the whole run over one corrupt byte."""
    state.mkdir(parents=True, exist_ok=True)
    (state / "projects.json").write_text(root, encoding="utf-8")

    indexing._update_project_registry("pid1", "C:/proj", files_indexed=5)

    written = json.loads((state / "projects.json").read_text(encoding="utf-8"))
    assert written["pid1"]["files_indexed"] == 5


def test_a_non_object_entry_does_not_hide_a_registered_one(tmp_path, monkeypatch):
    """Fail closed on the junk entry, not on the whole registry."""
    real = tmp_path / "proj"
    real.mkdir()
    monkeypatch.setattr(app_mod, "_list_projects",
                        lambda: {"junk": 5, "pid1": {"project_path": str(real)}})

    assert app_mod._registered_project_or_error(str(real), "runs tests") is None
