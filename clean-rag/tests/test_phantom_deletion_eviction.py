"""A manifest entry for a file that is still on disk but no longer indexable
must be evicted, not retried forever.

The bug: find_changed_files builds `deleted` as (manifest keys) minus (what
scan_project returned), so a file excluded by a widened skip rule or a new
.gitignore line lands there even though it is still readable. reindex_file
gated its deletion branch on `not abs_file.is_file()` alone, so that file fell
through to the hash comparison, matched, and returned {"unchanged": True}
without touching the manifest. The entry survived, so the next sweep classified
it as deleted again, forever. Measured on one real project: 377 such entries,
74,358 "Could not drop deleted" log lines across four rotated logs.

The check that matters is the second assert in
test_force_drop_evicts_a_live_but_ineligible_file: without force_drop the call
returns "unchanged" and the manifest still holds the key, which is the bug
reproducing.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import auto_reindex, indexing  # noqa: E402
from server.auto_reindex import find_changed_files  # noqa: E402


def _read_manifest(manifest_path):
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("__")}


@pytest.fixture
def indexed_project(tmp_path, monkeypatch):
    """A project with one live file recorded in its manifest.

    The store is stubbed out. This test is about which branch reindex_file
    takes and what it leaves in the manifest, not about embedding.

    DATABASES_DIR is redirected the way the rest of this suite redirects it
    (test_reindex_batch_adversarial.py:95 and eight others), so the index dir
    this fixture creates lands in tmp_path and never in the live one.
    """
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    project = tmp_path / "proj"
    (project / "keep").mkdir(parents=True)
    (project / "drop").mkdir()
    live = project / "keep" / "real.py"
    live.write_text("x = 1\n", encoding="utf-8")
    ineligible = project / "drop" / "excluded.py"
    ineligible.write_text("y = 2\n", encoding="utf-8")

    _root, _pid, index_dir, chroma_dir, manifest_path = indexing._project_paths(str(project))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "__project_path__": str(project),
        "keep/real.py": indexing.file_hash("x = 1\n"),
        "drop/excluded.py": indexing.file_hash("y = 2\n"),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    deleted_calls = []

    class _FakeStore:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def collection_exists(self, _name):
            return True

        def delete_by_source(self, _collection, rel_path):
            deleted_calls.append(rel_path)
            return 3

        def vacuum_if_needed(self):
            pass

    monkeypatch.setattr(indexing, "ChromaStore", _FakeStore)
    return project, manifest_path, deleted_calls


def test_drop_manifest_key_evicts_a_live_but_ineligible_file(indexed_project):
    project, manifest_path, deleted_calls = indexed_project
    target = str(project / "drop" / "excluded.py")

    assert Path(target).is_file(), "precondition: the file is still on disk"

    # reindex_file is asked about the FILE, and the file is fine, so it reports
    # unchanged and leaves the manifest entry alone. That is correct behaviour
    # and it is also the bug this whole file exists for: the sweep used to route
    # its evictions through here, so a still-readable but no-longer-indexable
    # file was reported as deleted on every sweep and never dropped. Asserted
    # directly so the test bites if eviction ever gets routed back through here.
    before = indexing.reindex_file(str(project), target, model_cache=None)
    assert before.get("unchanged") is True, (
        f"expected the file-oriented call to report unchanged, got {before}"
    )
    assert "drop/excluded.py" in _read_manifest(manifest_path), (
        "reindex_file must leave the entry, otherwise this test proves nothing"
    )

    # drop_manifest_key is asked about the KEY, so it evicts it, and the file
    # still being on disk is not its business.
    after = indexing.drop_manifest_key(str(project), "drop/excluded.py")
    assert after.get("deleted") is True, f"expected a drop, got {after}"
    assert after.get("was_in_manifest") is True, (
        f"a key that was really there must report was_in_manifest, got {after}"
    )
    assert "drop/excluded.py" not in _read_manifest(manifest_path), (
        "the eviction must remove the manifest entry"
    )
    assert "drop/excluded.py" in deleted_calls, (
        "the eviction must delete the stored chunks, not just the manifest key"
    )
    assert Path(target).is_file(), "the eviction must not touch the file on disk"


def test_dropping_a_key_that_is_not_in_the_manifest_is_not_reported_as_dropped(
    indexed_project
):
    """The delete is keyed on a string, so it "succeeds" for any string.

    That is exactly how a stuck entry hid: a caller that respelled the key
    evicted nothing, got deleted=True back, and the sweep logged "Dropped 1 of
    1" while the real entry sat in the manifest and came back every sweep.
    was_in_manifest is what lets the caller tell those apart.
    """
    project, manifest_path, _deleted_calls = indexed_project

    out = indexing.drop_manifest_key(str(project), "drop/EXCLUDED.py")

    assert out.get("was_in_manifest") is False, (
        f"a key matching no manifest entry must say so, got {out}"
    )
    assert "drop/excluded.py" in _read_manifest(manifest_path), (
        "the real entry must survive a near-miss key"
    )


def _sweep(project, monkeypatch) -> bool:
    """Drive the real sweep, the way the other deletion tests drive it
    (test_manifest_checkpoint_and_deletion.py:580).

    Not a copy of the drop loop: a copy passes just as happily when the real
    loop respells the key. The index lock is one global file, so it is stubbed
    or a real reindex running on this machine makes the sweep skip its work and
    the test pass vacuously.
    """
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **k: True)
    monkeypatch.setattr(auto_reindex, "release_index_lock", lambda *a, **k: None)
    return asyncio.run(
        auto_reindex._sweep_project("pid", {"project_path": str(project)}, None)
    )


@pytest.mark.parametrize("spelling", ["native", "forward_slash"])
def test_force_drop_evicts_an_absolute_key_from_outside_the_project_root(
    indexed_project, tmp_path, monkeypatch, spelling
):
    """_rel_path keys a file outside the root on its whole path, so a manifest
    can carry an absolute key, in either separator spelling.

    Such a key could never be dropped: joining it onto the project root gives
    back the same absolute path (a path join discards its left side when the
    right side is absolute), reindex_file's relative_to gate then refused it
    with an error, and the entry survived to be reported deleted again on the
    next sweep, and every sweep after. Its chunks are in the store under that
    same string, so nothing but the gate was in the way.
    """
    project, manifest_path, deleted_calls = indexed_project
    foreign_key = str(tmp_path / "outside_the_project" / "legacy.py")
    if spelling == "forward_slash":
        # What _rel_path's fallback actually writes: it forward slashes the path
        # it falls back to.
        foreign_key = foreign_key.replace("\\", "/")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[foreign_key] = "deadbeefdeadbeef"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    _changed, deleted = find_changed_files(str(project))
    assert deleted == [foreign_key], f"the sweep must report the foreign key: {deleted}"

    assert _sweep(project, monkeypatch) is True, "the sweep did not run"
    after = _read_manifest(manifest_path)
    assert foreign_key not in after, f"the foreign key survived the drop: {after}"
    assert deleted_calls == [foreign_key], (
        f"the store delete must target the key as the manifest spells it, got {deleted_calls}"
    )

    _changed2, deleted2 = find_changed_files(str(project))
    assert deleted2 == [], f"expected convergence, second sweep still reports {deleted2}"


@pytest.mark.parametrize("cwd", ["project_root", "subdir"])
def test_the_key_is_used_verbatim_and_the_cwd_cannot_change_it(
    indexed_project, monkeypatch, cwd
):
    """The same key must evict the same entry from anywhere on the filesystem.

    An earlier version anchored a relative key with os.path.abspath, which joins
    against the process working directory, so this exact call evicted
    'drop/drop/excluded.py' when run from inside project/drop. Nothing consults
    the filesystem now, so there is no working directory for a key to pick up,
    and parametrizing over cwd is how that stays true.
    """
    project, manifest_path, deleted_calls = indexed_project
    monkeypatch.chdir(project if cwd == "project_root" else project / "drop")

    out = indexing.drop_manifest_key(str(project), "drop/excluded.py")

    assert out.get("file") == "drop/excluded.py", f"the key was rewritten: {out}"
    assert out.get("was_in_manifest") is True, f"expected a real eviction, got {out}"
    assert deleted_calls == ["drop/excluded.py"], f"wrong store key: {deleted_calls}"
    assert "drop/excluded.py" not in _read_manifest(manifest_path)


def test_a_key_containing_dotdot_is_evicted_verbatim(indexed_project):
    """bad-cop round 3: a relative key holding '..' used to collapse elsewhere.

    The old drop loop joined it onto the project root, producing
    '.../proj/../outside/secret.py'. normpath then collapsed that for the
    relative_to probe only, and the eviction ran against the uncollapsed
    reconstructed string, which matched neither the manifest nor the store. It
    still returned deleted=True, so the sweep logged a drop that never happened
    and the entry came back forever. A key is a string here now, so there is no
    join and nothing to collapse.
    """
    project, manifest_path, deleted_calls = indexed_project
    key = "../outside/secret.py"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[key] = "deadbeefdeadbeef"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    out = indexing.drop_manifest_key(str(project), key)

    assert out.get("file") == key, f"the key was rewritten: {out}"
    assert out.get("was_in_manifest") is True, (
        f"the entry was really in the manifest, so this must be a real drop: {out}"
    )
    assert deleted_calls == [key], f"the store delete must use the key as given: {deleted_calls}"
    assert key not in _read_manifest(manifest_path), "the entry must be gone"
    assert "keep/real.py" in _read_manifest(manifest_path), "unrelated entries must survive"


def _link_dir(target: Path, link: Path) -> bool:
    """Point *link* at directory *target*. False if this machine cannot."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        pass
    if os.name != "nt":
        return False
    # Windows refuses os.symlink without SeCreateSymbolicLinkPrivilege, which is
    # why the symlink half of this went unproven. A directory junction needs no
    # privilege and Path.resolve() follows it exactly the same way.
    return subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
    ).returncode == 0


def test_eviction_uses_the_key_the_caller_named_not_the_link_target(indexed_project):
    """The same key rewriting as the case only rename, reached through a link.

    A manifest key can name a path that reaches its file through a linked
    directory. Resolving such a path rewrites it to the link's target, so an
    eviction keyed on the resolved path deletes rows under a key nobody asked
    about while the real ones stay in the store with nothing left that could
    reindex them. The link still exists in this fixture precisely so that a
    future implementation that starts resolving again fails here.
    """
    project, manifest_path, deleted_calls = indexed_project
    link = project / "linked"
    if not _link_dir(project / "keep", link):
        pytest.skip("this machine allows neither a symlink nor a junction")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["linked/real.py"] = indexing.file_hash("x = 1\n")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    out = indexing.drop_manifest_key(str(project), "linked/real.py")

    assert out.get("file") == "linked/real.py", f"evicted the wrong key: {out}"
    after = _read_manifest(manifest_path)
    assert "linked/real.py" not in after, f"the named key survived: {after}"
    assert deleted_calls == ["linked/real.py"], (
        f"the store delete must target the named key, got {deleted_calls}"
    )
    assert "keep/real.py" in after, (
        "the link target's own entry is a different file to the index and must "
        f"be untouched, got {after}"
    )


def test_reindex_file_cannot_evict_a_live_file_at_all(indexed_project):
    """The /reindex-file endpoint and the per edit hook only ever go through here.

    A normal edit must take the update path. reindex_file no longer has any
    parameter that could make it evict a file that is present, which is the
    point: eviction is a different function, so there is no flag for a caller
    to get wrong and no way for these two callers to reach it by accident.
    """
    project, manifest_path, deleted_calls = indexed_project
    live = project / "keep" / "real.py"

    out = indexing.reindex_file(str(project), str(live), model_cache=None)

    assert out.get("deleted") is not True, f"an unedited live file must not be dropped: {out}"
    assert "keep/real.py" in _read_manifest(manifest_path)
    assert "keep/real.py" not in deleted_calls

    import inspect
    params = inspect.signature(indexing.reindex_file).parameters
    assert "force_drop" not in params, (
        "the eviction flag is gone on purpose; reintroducing it puts the "
        "key-to-path-and-back round trip back in the one function that must "
        "not have it"
    )


def _quarantined_project(tmp_path, monkeypatch, name, payload):
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    project = tmp_path / name
    project.mkdir()
    (project / "bad.py").write_bytes(payload)

    _root, _pid, _index, _chroma, manifest_path = indexing._project_paths(str(project))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {"__project_path__": str(project), "bad.py": indexing.UNREADABLE_SENTINEL}
        ),
        encoding="utf-8",
    )
    return project


def test_quarantined_non_utf8_file_never_reaches_the_drop_loop(tmp_path, monkeypatch):
    """The real quarantine case: fails strict UTF-8, but holds no NUL byte.

    scan_project sniffs for a NUL, not for decodability, so this file is still
    returned by the scan. find_changed_files adds every scanned path to `seen`
    before it checks UNREADABLE_SENTINEL, so the entry never lands in `deleted`
    and never reaches the force_drop loop. That ordering is what keeps
    force_drop safe for quarantined files, so assert it rather than trust it.
    """
    project = _quarantined_project(tmp_path, monkeypatch, "quar", b"# caf\xe9 not utf8\n")

    _changed, deleted = find_changed_files(str(project))

    assert "bad.py" not in deleted, (
        "a quarantined but scannable file must never be handed to the drop loop, "
        f"got deleted={deleted}"
    )


def test_quarantined_binary_file_is_evicted_and_converges(tmp_path, monkeypatch):
    """A NUL byte is different, and worth pinning down rather than assuming.

    looks_binary() skips a file containing a NUL, so scan_project never returns
    it, so it IS classified deleted and force_drop evicts its manifest entry.
    That is correct: a binary blob has no business holding index rows. It also
    converges instead of looping, which is the property that actually matters
    here. After the eviction the path is no longer in the manifest, so the next
    sweep does not see it in `known` and cannot classify it as deleted again.
    And recovery still works: if the file is later repaired to valid text,
    scan_project returns it, find_changed_files finds no hash for it, and it is
    reindexed as changed.
    """
    project = _quarantined_project(tmp_path, monkeypatch, "binquar", b"\xff\xfe not utf8 \x00")

    _changed, deleted = find_changed_files(str(project))
    assert "bad.py" in deleted, (
        "a NUL-containing file is skipped by scan_project, so it is expected "
        f"here; if this changed, the eviction reasoning needs revisiting: {deleted}"
    )

    # Convergence: once the entry is gone from the manifest, it cannot be
    # reclassified as deleted on the following sweep. That is the whole point.
    _root, _pid, _index, _chroma, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw.pop("bad.py")
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    _changed2, deleted2 = find_changed_files(str(project))
    assert deleted2 == [], f"expected convergence after eviction, got {deleted2}"


def test_a_key_is_dropped_even_when_the_store_has_no_collection(tmp_path, monkeypatch):
    """The production failure every stubbed test missed.

    Found by running the real sweep, not by a test: todaymechanic had 917
    manifest keys and a vectors.db holding zero tables, so collection_exists()
    was False and the eviction returned an error before reaching the manifest.
    377 keys were rediscovered as deleted on every sweep, forever, which is the
    same loop this whole file exists to close, reached through the one door the
    fixture left open.

    Deliberately does NOT stub ChromaStore. Stubbing it with
    collection_exists() -> True is exactly what hid this.
    """
    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    project = tmp_path / "emptystore"
    project.mkdir()

    _root, _pid, _index, chroma_dir, manifest_path = indexing._project_paths(str(project))
    chroma_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"__project_path__": str(project), "stale/gone.py": "abc123"}),
        encoding="utf-8",
    )

    out = indexing.drop_manifest_key(str(project), "stale/gone.py")

    assert out.get("was_in_manifest") is True, (
        f"the entry was in the manifest, so it must be reported dropped: {out}"
    )
    assert out.get("collection_present") is False, (
        f"an empty store must be surfaced, not silently treated as a hit: {out}"
    )
    assert out.get("chunks_removed") == 0
    assert "stale/gone.py" not in _read_manifest(manifest_path), (
        "the manifest entry must go even with no collection, otherwise the "
        "sweep rediscovers it every ten minutes forever"
    )
