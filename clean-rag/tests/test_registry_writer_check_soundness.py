"""Does the removal only check catch every way a writer adds a registry entry?

test_a_removal_only_writer_really_cannot_add in
test_exec_routes_require_registered_project.py is what earns a place on
_REMOVAL_ONLY_WRITERS: it has to fail the day an allowlisted "removal only"
writer (currently indexing.py:_remove_from_project_registry) gains the ability
to add an entry to state/projects.json, the file that gates the exec routes.

That check used to read the writer's source and decide from the syntax. Six
spellings below defeat that idea, and the first five each defeated the real
implementation in turn: a plain subscript store is the obvious one, then a
dict merge reassignment, dict.__setitem__, operator.setitem, a local rebinding
of a name the allowlist already permitted, and finally a bare call to such a
name bound one scope up, which the function's own source cannot distinguish
from the dict read the allowlist meant. Each new spelling cost a round.

The check is now the registry file itself, watched from the first instant of
the call to the last, so the spelling stops mattering. These stay as fixtures
because they are the evidence for that: each one really does put a key in the
file when it runs, and the check has to report every one. A seventh spelling
nobody has thought of needs no change here, which is the point.

Watching throughout rather than only at the ends is the second round of the
same lesson. Before against after missed a writer that added a key, wrote it,
then removed it and wrote again, because the file ends where it started. The
key was readable on disk in between, and the writer runs in an executor thread
while the event loop serves other requests, so an instant is long enough to
spend it. The transient cases below are that shape, one per write path it can
take.

What this cannot do is cover a writer no drive exercises. That limit is stated
where the drives live, in the test named above.
"""
import ctypes
import json
import operator  # noqa: F401 - one case resolves operator.setitem through it
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_exec_routes_require_registered_project import (  # noqa: E402
    _keys_added_by,
    _registry_keys,
    _seed_registry,
)

#: Every case is shaped like the real remover: read STATE_DIR/projects.json,
#: do its thing, write the file back. Only the marked line differs, so the
#: spelling is the single variable between them.
_SHAPE = '''
def _remove_from_project_registry(project_path):
    registry_path = STATE_DIR / "projects.json"
    if not registry_path.exists():
        return []
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
{body}
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return []
'''

#: label -> (the body that adds a key, extra names its namespace needs)
_CASES = {
    "subscript store": (
        '    registry["new-pid"] = {"project_path": project_path}',
        {},
    ),
    "dict merge reassignment": (
        '    registry = {**registry, "new-pid": {"project_path": project_path}}',
        {},
    ),
    "dict.__setitem__": (
        '    dict.__setitem__(registry, "new-pid", {"project_path": project_path})',
        {},
    ),
    "operator.setitem": (
        '    operator.setitem(registry, "new-pid", {"project_path": project_path})',
        {"operator": operator},
    ),
    # Never spells a disallowed call. It binds a mutating bound method to a
    # name the old allowlist permitted, so the call site reads as a dict get.
    "rebinding an allowed name (get = registry.setdefault)": (
        '    get = registry.setdefault\n'
        '    get("new-pid", {"project_path": project_path})',
        {},
    ),
    # The mirror of the one above, moved one scope out. Nothing in the
    # function binds `get`, so it resolves through the module namespace, and
    # the function's own source says nothing about what it is.
    "free variable bound one scope up (get is dict.__setitem__)": (
        '    get(registry, "new-pid", {"project_path": project_path})',
        {"get": dict.__setitem__},
    ),
}

_SEED = {"existing-pid": {"project_path": "C:/already/indexed"}}


def _writer_for(body, extras, state_dir):
    namespace = {"STATE_DIR": state_dir, "json": json, **extras}
    source = _SHAPE.format(body=body)
    exec(compile(source, "<adversarial>", "exec"), namespace)  # noqa: S102 - test-only, fixed source
    return namespace["_remove_from_project_registry"]


def _scratch_registry(tmp_path, seed=_SEED):
    state = tmp_path / "state"
    state.mkdir()
    registry_path = state / "projects.json"
    _seed_registry(registry_path, seed)
    return state, registry_path


@pytest.mark.parametrize("label", list(_CASES))
def test_the_check_catches_every_real_way_to_add_an_entry(label, tmp_path):
    body, extras = _CASES[label]
    state, registry_path = _scratch_registry(tmp_path)
    writer = _writer_for(body, extras, state)

    added = _keys_added_by(lambda: writer("C:/some/path"), registry_path)

    assert added == {"new-pid"}, (
        f"the removal only check missed: {label}. The writer put a key in "
        f"state/projects.json, which is the exec route allowlist, and the "
        f"check reported {sorted(added)}. A writer built this way would pass "
        f"test_a_removal_only_writer_really_cannot_add while being able to "
        f"register a project nothing ever indexed."
    )


def _transient_via_two_write_texts(registry_path):
    """Write the key, write it away again. The file ends where it started."""
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["new-pid"] = {"project_path": "C:/never/indexed"}
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    del registry["new-pid"]
    registry_path.write_text(json.dumps(registry), encoding="utf-8")


def _transient_through_one_handle(registry_path):
    """Both states through a single open handle, which raises one audit event.

    The flush is what puts the added key on disk. Reading it from a second
    handle while this one is still open works on Windows, so the window is
    real rather than a technicality.
    """
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    with registry_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({**registry, "new-pid": {"project_path": "C:/never"}}))
        handle.flush()
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(registry))


def _transient_by_renaming_over_the_registry(registry_path):
    """Never opens the registry for writing at all, renames onto it twice."""
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for content in ({**registry, "new-pid": {"project_path": "C:/never"}}, registry):
        staged = registry_path.with_suffix(".staged")
        staged.write_text(json.dumps(content), encoding="utf-8")
        os.replace(staged, registry_path)


def _short_name_of(path):
    """The volume's 8.3 alias for *path*, or None when it has none.

    ctypes rather than the ``dir /x`` shape used elsewhere in this suite,
    because a subprocess raises an opaque audit event that the watch is right
    to refuse, and the case would then prove nothing about the spelling.
    """
    if sys.platform != "win32":
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer)):
        return None
    short = buffer.value
    if os.path.normcase(short) == os.path.normcase(str(path)):
        return None
    return short


def _transient_through_a_hard_link(registry_path):
    """The same two writes, reached by a second name for the same file.

    A hard link is a second directory entry pointing at one file, so the two
    paths share every byte and no string normalizer folds them together.
    """
    alias = registry_path.with_name("projects_alias.json")
    try:
        os.link(registry_path, alias)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this filesystem cannot create a hard link: {exc}")
    _transient_via_two_write_texts(alias)


def _transient_through_an_8_3_short_name(registry_path):
    """The same two writes, reached by the volume's generated short name.

    A different alias mechanism from the hard link above and the same class of
    hole. It is here as well as the hard link because 8.3 generation can be
    turned off per volume, so neither one alone runs everywhere.
    """
    short = _short_name_of(registry_path)
    if short is None:
        pytest.skip("8.3 name generation is off on this volume")
    _transient_via_two_write_texts(Path(short))


_TRANSIENT_CASES = {
    "two write_text calls": _transient_via_two_write_texts,
    "one handle, flushed between writes": _transient_through_one_handle,
    "renamed over twice": _transient_by_renaming_over_the_registry,
    "through a hard link to the same file": _transient_through_a_hard_link,
    "through an 8.3 short name": _transient_through_an_8_3_short_name,
}


@pytest.mark.parametrize("label", list(_TRANSIENT_CASES))
def test_the_check_catches_a_key_that_only_exists_mid_call(label, tmp_path):
    """The key is gone by the time the writer returns, and it still counts.

    delete_project_index runs the writer in an executor thread, so the event
    loop is serving other requests throughout. A registry key readable for an
    instant is a key a concurrent /run-tests can read and spend.
    """
    _, registry_path = _scratch_registry(tmp_path)

    added = _keys_added_by(
        lambda: _TRANSIENT_CASES[label](registry_path), registry_path,
    )

    assert added == {"new-pid"}, (
        f"the removal only check missed an add partway through the call: "
        f"{label}. The key was "
        f"on disk and readable during the call and the check reported "
        f"{sorted(added)}, which is what comparing only the file before "
        f"against the file after reports for every writer of this shape."
    )
    assert _registry_keys(registry_path) == set(_SEED), (
        "test setup: the writer was supposed to leave the registry exactly as "
        "it found it, so before against after really does see nothing"
    )


def _writes_through_a_raw_descriptor(registry_path):
    fd = os.open(registry_path, os.O_WRONLY | os.O_TRUNC)
    try:
        os.write(fd, json.dumps({**_SEED, "new-pid": {}}).encode())
    finally:
        os.close(fd)


def _escapes_the_handle_it_was_given(registry_path):
    with registry_path.open("w", encoding="utf-8") as handle:
        os.write(handle.fileno(), json.dumps({**_SEED, "new-pid": {}}).encode())


_UNWATCHABLE_CASES = {
    "os.open and os.write": _writes_through_a_raw_descriptor,
    "fileno off the open handle": _escapes_the_handle_it_was_given,
}


@pytest.mark.parametrize("label", list(_UNWATCHABLE_CASES))
def test_the_check_fails_loudly_on_a_write_it_cannot_watch(label, tmp_path):
    """Not seeing a write and seeing no add have to be different answers.

    Both routes here put writes somewhere the observation does not reach. The
    honest result is a red test naming what could not be watched, because the
    alternative is the shape this whole check replaced: a confident "nothing
    added" about bytes nobody looked at.
    """
    _, registry_path = _scratch_registry(tmp_path)

    with pytest.raises(AssertionError, match="could not watch"):
        _keys_added_by(lambda: _UNWATCHABLE_CASES[label](registry_path), registry_path)


class _NoFileId:
    """A stat result carrying no file id, which is what a FAT volume, a CIFS
    share (python/cpython#105212) and an unopenable file (#111877) report."""

    st_ino = 0

    def __init__(self, st):
        self._st = st

    def __getattr__(self, name):
        return getattr(self._st, name)


def _report_no_file_id_for(monkeypatch, blind):
    """Make os.stat report st_ino 0 for every path *blind* accepts.

    Only string spellings, so pytest's own stat calls around the drive keep
    their real results.
    """
    real_stat = os.stat

    def blinded(path, *args, **kwargs):
        st = real_stat(path, *args, **kwargs)
        return _NoFileId(st) if isinstance(path, str) and blind(path) else st

    monkeypatch.setattr(os, "stat", blinded)


def test_a_path_the_filesystem_will_not_identify_is_refused_not_passed(
    tmp_path, monkeypatch,
):
    """Identity is what separates an alias from an unrelated file.

    So a volume that will not report identity leaves the watch unable to tell
    the two apart, and the honest answer is the one it gives for a write it
    cannot see: red, naming the path. st_ino 0 is the real shape of this
    rather than a hypothetical, reported for every file by FAT and by some
    network shares, and os.path.samestat calls two such files identical.
    """
    _, registry_path = _scratch_registry(tmp_path)
    _report_no_file_id_for(monkeypatch, lambda path: path.endswith(".json"))

    def writes_a_sibling(registry_path=registry_path):
        registry_path.with_name("other.json").write_text("{}", encoding="utf-8")

    with pytest.raises(AssertionError, match="could not watch"):
        _keys_added_by(writes_a_sibling, registry_path)


@pytest.mark.parametrize(
    "seed", [_SEED, None], ids=["registry on disk", "registry not written yet"],
)
def test_an_unrelated_devnull_open_during_the_window_is_not_reported_as_unwatched(
    seed, tmp_path,
):
    """Refusing what cannot be identified must not refuse a device.

    os.devnull is opened by subprocess redirects, null log handlers and any
    library silencing its own output, and on Windows it resolves to the DOS
    device path. os.stat succeeds on it and reports st_ino 0, because it is a
    character device rather than a file with an id. Reading that as "might be
    the registry" turned failing closed into failing on a writer that never
    went near the file.
    """
    _, registry_path = _scratch_registry(tmp_path, seed)

    def discards_some_output():
        with open(os.devnull, "w", encoding="utf-8") as sink:
            sink.write("this is not the registry")

    added = _keys_added_by(discards_some_output, registry_path)

    assert added == set(), (
        f"a writer that only opened {os.devnull} was reported as adding "
        f"{sorted(added)}, so any writer that discards output fails a check "
        f"about a file it never touched"
    )


def test_a_volume_with_no_file_ids_refuses_the_run_once_and_names_itself(
    tmp_path, monkeypatch,
):
    """Refuse the whole check, not whichever file the writer happened to open.

    On a volume that identifies nothing, every path is indistinguishable from
    an alias of the registry, so there is no sound answer to give and the
    check cannot run there. Said once, about the registry's own volume, it is
    actionable. Said per path it reads as an accusation against an unrelated
    file and grows a line for every open the writer makes.
    """
    _, registry_path = _scratch_registry(tmp_path)
    _report_no_file_id_for(monkeypatch, lambda path: True)

    def writes_an_unrelated_file(registry_path=registry_path):
        registry_path.with_name("unrelated.log").write_text("hi", encoding="utf-8")

    with pytest.raises(AssertionError, match="no file id of its own") as refusal:
        _keys_added_by(writes_an_unrelated_file, registry_path)

    assert "unrelated.log" not in str(refusal.value), (
        f"the refusal blames a file the writer was entitled to open, rather "
        f"than the volume that cannot identify anything: {refusal.value}"
    )


def test_an_alias_with_no_file_id_is_refused_rather_than_missed(
    tmp_path, monkeypatch,
):
    """A missing file id on one spelling must not read as a different file.

    Windows hands back st_ino 0 for a real file often enough to matter: over
    CIFS (python/cpython#105212) and for a file it will not open
    (python/cpython#111877). Treating 0 as a value to compare makes that
    spelling look like some other file, and a write through it disappears.
    Compared as an absence it fails closed, which is the direction this whole
    mechanism exists to hold.
    """
    _, registry_path = _scratch_registry(tmp_path)
    alias = registry_path.with_name("projects_alias.json")
    try:
        os.link(registry_path, alias)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this filesystem cannot create a hard link: {exc}")
    _report_no_file_id_for(monkeypatch, lambda path: path.endswith(alias.name))

    with pytest.raises(AssertionError, match="could not watch"):
        _keys_added_by(lambda: _transient_via_two_write_texts(alias), registry_path)


def test_an_atomic_rename_writer_is_watched_rather_than_refused(tmp_path):
    """Failing closed must not mean failing on every writer worth having.

    Staging a temp file and renaming it over the target is the ordinary way to
    replace a file without a torn read. A remover written that way is fully
    observed, so it has to come back clean, not unwatchable.
    """
    _, registry_path = _scratch_registry(
        tmp_path, {**_SEED, "doomed-pid": {"project_path": "C:/going"}},
    )

    def remove_by_rename():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        del registry["doomed-pid"]
        staged = registry_path.with_suffix(".staged")
        staged.write_text(json.dumps(registry), encoding="utf-8")
        os.replace(staged, registry_path)

    added = _keys_added_by(remove_by_rename, registry_path)

    assert added == set(), (
        f"a remover that stages and renames was reported as adding "
        f"{sorted(added)}, so the check now refuses the safest way to write "
        f"the file and the removal only allowlist is unearnable"
    )
    assert _registry_keys(registry_path) == {"existing-pid"}, (
        "the remover did not actually remove, so this case proves nothing"
    )


def test_a_writer_that_only_removes_adds_nothing(tmp_path):
    """Reporting an add for everything would satisfy the cases above and say
    nothing. A real remover has to come back clean."""
    body = (
        '    for pid, entry in list(registry.items()):\n'
        '        if (entry or {}).get("project_path") == project_path:\n'
        '            del registry[pid]'
    )
    state, registry_path = _scratch_registry(
        tmp_path, {**_SEED, "doomed-pid": {"project_path": "C:/going"}},
    )
    writer = _writer_for(body, {}, state)

    added = _keys_added_by(lambda: writer("C:/going"), registry_path)

    assert added == set(), (
        "the check now reports an add for a writer that only deletes, so the "
        "removal only allowlist is unearnable and the rule it enforces is dead"
    )
    assert _registry_keys(registry_path) == {"existing-pid"}, (
        "the remover did not actually remove, so this case proves nothing "
        "about a check that has to tell removing apart from adding"
    )
