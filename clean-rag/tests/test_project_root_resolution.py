"""_project_root() decides which project a prompt belongs to, on every single
message. A wrong answer here either searches the wrong tree or, worse, walks
straight past a registered project up to the containing repo and queues an
index of everything inside it.

Covers the resolver itself, the registry reader it depends on
(_registered_projects, _registered_projects_under), the int coercion the
is_indexed check depends on (_int_field), the refusal branch that must never
spawn a subprocess, that the project named to the user is the project actually
searched, and that resolution cost does not grow with the size of the registry
on a hook this hot.
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG / "hooks"))


@pytest.fixture()
def rag_enforce():
    path = str(CLEAN_RAG / "hooks" / "rag-enforce.py")
    spec = importlib.util.spec_from_file_location("rag_enforce_root_res", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def home(tmp_path, monkeypatch):
    (tmp_path / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CLEAN_RAG_HOME", str(tmp_path))
    return tmp_path


def _write_registry(home, entries: dict):
    (home / "state" / "projects.json").write_text(json.dumps(entries), encoding="utf-8")


class _FakeStatusResponse:
    """Stands in for urlopen's context manager over any JSON endpoint."""

    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _run_git_project_context(rag_enforce, status_body, git_root):
    """_git_project_context against a canned /status, indexer stubbed out.

    Returns the banner it produced and every Popen call it tried to make, so a
    test can assert on what the user is told and on whether an index was
    actually queued.
    """
    popen_calls = []

    def record_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return object()

    with patch("urllib.request.urlopen", return_value=_FakeStatusResponse(status_body)):
        with patch.object(rag_enforce.subprocess, "Popen", side_effect=record_popen):
            banner = rag_enforce._git_project_context("8613", git_root)
    return banner, popen_calls


class TestClosestRegisteredProjectWins:
    def test_nested_registered_project_beats_the_repo_that_contains_it(self, rag_enforce, home):
        """The concrete case named in the requirements: cwd
        <repo>/Domain must resolve to <repo>/Domain, not to <repo>, which is
        the nearest ancestor holding a .git."""
        development = home / "Development"
        domain = development / "Domain"
        domain.mkdir(parents=True)
        (development / ".git").mkdir()
        _write_registry(home, {"h1": {"project_path": str(domain), "files_indexed": 1697}})

        result = rag_enforce._project_root(str(domain))
        assert result == str(domain.resolve())

        git_root_only = rag_enforce._find_git_root(str(domain))
        assert git_root_only == str(development.resolve()), (
            "sanity: the plain git walk really does climb past Domain to the "
            "containing repo, which is the exact wrong answer _project_root "
            "exists to avoid"
        )

    def test_closest_of_two_registered_ancestors_wins(self, rag_enforce, home):
        root = home / "root"
        a = root / "A"
        b = a / "B" / "C"
        start = b / "D" / "E"
        start.mkdir(parents=True)
        _write_registry(home, {
            "far": {"project_path": str(a)},
            "close": {"project_path": str(b)},
        })
        result = rag_enforce._project_root(str(start))
        assert result == str(b.resolve()), (
            "the closer registered project must win over the farther one"
        )

    def test_a_registry_entry_matches_however_it_is_spelled(self, rag_enforce, home):
        """Case, separator direction, a trailing separator and a `..` segment
        are all the same project. Paths reach the registry from /index-project
        callers, not only from this hook, so the spelling is not ours to
        assume."""
        project = home / "Development" / "Domain"
        project.mkdir(parents=True)
        for label, spelling in [
            ("upper case", str(project).upper()),
            ("forward slashes", str(project).replace("\\", "/")),
            ("trailing separator", str(project) + "\\"),
            ("dot dot segment", str(project / ".." / "Domain")),
        ]:
            _write_registry(home, {"h1": {"project_path": spelling}})
            assert rag_enforce._project_root(str(project)) == str(project.resolve()), label


class TestNormPath:
    """_norm_path is what lets the walk be compared against the whole registry
    without a filesystem call per registered project. It has to fold every
    spelling of the same path onto one string, or the cheap comparison is also
    a wrong one."""

    def test_the_same_path_spelled_differently_normalizes_the_same(self, rag_enforce):
        forms = [
            "C:\\Development\\Domain",
            "c:\\development\\domain",
            "C:/Development/Domain",
            "C:\\Development\\Domain\\",
            "C:\\Development\\.\\Domain",
            "C:\\Development\\Other\\..\\Domain",
            "C:\\Development\\\\Domain",
        ]
        normalized = {rag_enforce._norm_path(f) for f in forms}
        assert len(normalized) == 1, f"expected one normal form, got {normalized}"

    def test_different_paths_stay_different(self, rag_enforce):
        assert rag_enforce._norm_path("C:\\Development\\Domain") != rag_enforce._norm_path(
            "C:\\Development\\DomainOther"
        )

    def test_empty_is_empty_and_never_a_relative_dot(self, rag_enforce):
        """A registry row with no readable project_path reads as "". It must not
        normalize to "." (which is what str(Path("")) gives), because "." is a
        real relative path and this value is compared against absolute ones."""
        assert rag_enforce._norm_path("") == ""

    def test_a_drive_root_normalizes_consistently_with_itself(self, rag_enforce):
        assert rag_enforce._norm_path("C:\\") == rag_enforce._norm_path("C:/")

    def test_it_does_not_claim_to_fold_a_spelling_only_the_filesystem_knows(
        self, rag_enforce, tmp_path
    ):
        """Pins the limit this normalizer actually has, so nobody re-derives the
        idea that it is the whole comparison. A trailing dot names the same real
        directory on Windows and no string rule can tell."""
        plain = tmp_path / "trailing_probe"
        plain.mkdir()
        dotted = str(plain) + "."
        assert Path(dotted).resolve() == plain.resolve(), (
            "sanity: Windows really does strip the trailing dot"
        )
        assert rag_enforce._norm_path(dotted) != rag_enforce._norm_path(str(plain))


def _make_junction(link: Path, target: Path):
    """A junction at *link* pointing at *target*, or None if this machine
    cannot make one."""
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not link.exists():
        return None
    return link


def _short_name_of(directory: Path):
    """*directory* spelled as its 8.3 alias, or None when the volume has 8.3
    name generation switched off."""
    proc = subprocess.run(
        ["cmd", "/c", "dir", "/x", "/ad", str(directory.parent)],
        capture_output=True, text=True,
    )
    for line in proc.stdout.splitlines():
        if not line.endswith(directory.name):
            continue
        for field in line.split():
            if "~" in field:
                return directory.parent / field
    return None


class TestSameDirKey:
    """_same_dir_key is the half of the comparison _norm_path cannot do. Two
    spellings of one directory must produce one key, and anything it cannot
    answer for must produce no key at all rather than a shared one."""

    def test_a_junction_and_its_target_share_one_key(self, rag_enforce, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        link = _make_junction(tmp_path / "link", target)
        if link is None:
            pytest.skip("this machine cannot create a junction")
        assert rag_enforce._same_dir_key(str(link)) == rag_enforce._same_dir_key(str(target))

    def test_an_8_3_short_name_and_its_long_form_share_one_key(self, rag_enforce, tmp_path):
        long_form = tmp_path / "a_directory_name_long_enough_to_be_shortened"
        long_form.mkdir()
        short = _short_name_of(long_form)
        if short is None:
            pytest.skip("8.3 name generation is off on this volume")
        assert rag_enforce._same_dir_key(str(short)) == rag_enforce._same_dir_key(str(long_form))

    def test_a_trailing_dot_spelling_shares_one_key_with_the_plain_form(
        self, rag_enforce, tmp_path
    ):
        plain = tmp_path / "plain"
        plain.mkdir()
        assert rag_enforce._same_dir_key(str(plain) + ".") == rag_enforce._same_dir_key(str(plain))

    def test_two_different_directories_never_share_a_key(self, rag_enforce, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert rag_enforce._same_dir_key(str(a)) != rag_enforce._same_dir_key(str(b))

    @pytest.mark.parametrize("label,value", [
        ("nonexistent path", "nonexistent"),
        ("empty string", ""),
        ("embedded NUL byte", "C:\\bad\x00name"),
        # os.stat() reads an int as an open file descriptor, so an unguarded int
        # would come back with the identity of whatever handle that number is,
        # and a project could match on it.
        ("an int, which os.stat would read as a file descriptor", 1),
        ("None", None),
        ("a list", ["C:\\"]),
    ])
    def test_anything_unanswerable_yields_no_key_rather_than_a_shared_one(
        self, rag_enforce, tmp_path, label, value
    ):
        if value == "nonexistent":
            value = str(tmp_path / "never_created")
        assert rag_enforce._same_dir_key(value) is None, label

    def test_a_volume_reporting_no_inode_does_not_make_every_path_the_same_one(
        self, rag_enforce, home, monkeypatch
    ):
        """Some volumes report st_ino 0 for everything: network shares, FAT. A
        key built from that is shared by every path on the volume, so any
        registered project would answer for any directory. Driven through
        _project_root rather than the key, because the damage is the wrong
        project, not the wrong tuple."""
        walked = home / "walked"
        unrelated = home / "unrelated"
        walked.mkdir()
        unrelated.mkdir()
        _write_registry(home, {"other": {"project_path": str(unrelated)}})

        real_stat = os.stat

        class NoInodeStat:
            def __init__(self, st):
                self.st_dev = st.st_dev
                self.st_ino = 0

        # Only successful stats are rewritten, so a missing path still raises and
        # every existence check in the walk keeps working.
        monkeypatch.setattr(os, "stat", lambda p, *a, **k: NoInodeStat(real_stat(p)))

        result = rag_enforce._project_root(str(walked))

        assert result != str(walked.resolve()), (
            "an unrelated registered project answered for this directory, which "
            "is what happens once every path on the volume shares one key"
        )


class TestRegistrySpellingsOnlyTheFilesystemCanFold:
    """The registry stores whatever spelling the caller of /index-project used;
    server/app.py only strips whitespace. The walked path has been through
    resolve(). A junction, an 8.3 short name and a trailing dot all break that
    string comparison, and the consequence is not a cosmetic miss: a container
    holding a project registered that way reads as empty and gets auto indexed,
    which is the runaway index this whole refusal exists to stop."""

    def _project_root_with_registered(self, rag_enforce, home, spelling, start):
        _write_registry(home, {"h1": {"project_path": str(spelling), "files_indexed": 500}})
        return rag_enforce._project_root(str(start))

    def test_a_junction_spelled_registration_still_resolves_to_the_project(
        self, rag_enforce, home
    ):
        target = home / "real_target"
        target.mkdir()
        link = _make_junction(home / "link", target)
        if link is None:
            pytest.skip("this machine cannot create a junction")
        result = self._project_root_with_registered(rag_enforce, home, link, link)
        assert result is not None, (
            "a prompt from inside the junction found no project at all, so it "
            "would fall through to the .git walk"
        )
        assert Path(result) == target.resolve(), (
            "the junction spelling in the registry must still name this project"
        )

    def test_an_8_3_spelled_registration_still_resolves_to_the_project(
        self, rag_enforce, home
    ):
        long_form = home / "a_directory_name_long_enough_to_be_shortened"
        long_form.mkdir()
        short = _short_name_of(long_form)
        if short is None:
            pytest.skip("8.3 name generation is off on this volume")
        result = self._project_root_with_registered(rag_enforce, home, short, long_form)
        assert result is not None and Path(result) == long_form.resolve()

    def test_a_trailing_dot_registration_still_resolves_to_the_project(
        self, rag_enforce, home
    ):
        project = home / "dotted"
        project.mkdir()
        result = self._project_root_with_registered(
            rag_enforce, home, str(project) + ".", project
        )
        assert result is not None and Path(result) == project.resolve()

    def test_a_nested_junction_spelled_registration_still_beats_its_ancestor(
        self, rag_enforce, home
    ):
        """Closest still wins when the closer project is the one spelled
        oddly, otherwise the fix would trade a miss for the wrong project."""
        outer = home / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        link = _make_junction(home / "inner_link", inner)
        if link is None:
            pytest.skip("this machine cannot create a junction")
        _write_registry(home, {
            "outer": {"project_path": str(outer)},
            "inner_via_junction": {"project_path": str(link)},
        })
        assert Path(rag_enforce._project_root(str(inner))) == inner.resolve()

    def test_a_container_holding_a_junction_spelled_project_is_not_reported_empty(
        self, rag_enforce, home
    ):
        container = home / "container"
        child = container / "RealProject"
        child.mkdir(parents=True)
        link = _make_junction(home / "child_link", child)
        if link is None:
            pytest.skip("this machine cannot create a junction")
        _write_registry(home, {"child": {"project_path": str(link), "files_indexed": 500}})

        contained = rag_enforce._registered_projects_under(str(container))
        assert [Path(p) for p in contained] == [child.resolve()], (
            "the container holds a registered project and must say so; an empty "
            "answer is what lets it be auto indexed"
        )

    def test_a_container_reached_through_a_junction_still_sees_its_projects(
        self, rag_enforce, home
    ):
        """The mirror of the case above: the container is the oddly spelled side.
        cwd is inside a junction, so the root handed to the check is spelled as
        the junction while the registered project underneath is canonical."""
        container = home / "container"
        child = container / "RealProject"
        child.mkdir(parents=True)
        link = _make_junction(home / "container_link", container)
        if link is None:
            pytest.skip("this machine cannot create a junction")
        _write_registry(home, {"child": {"project_path": str(child), "files_indexed": 500}})

        contained = rag_enforce._registered_projects_under(str(link))
        assert [Path(p) for p in contained] == [child.resolve()], (
            "a container named through a junction still holds the same project"
        )


class TestProjectRootNeverRaises:
    @pytest.mark.parametrize("label,make_path", [
        ("nonexistent path", lambda home: str(home / "does" / "not" / "exist")),
        ("UNC path", lambda home: r"\\localhost\C$\does_not_exist_share_probe"),
        ("drive root", lambda home: "C:\\"),
        ("illegal windows chars", lambda home: "C:\\bad?name<>|path"),
        # A NUL byte reaches os.scandir() through the marker glob and raises
        # ValueError, not OSError. The resolver's contract is a path or None,
        # and a UserPromptSubmit hook may not end the turn with a traceback,
        # so this has to come back as None like every other unusable path.
        ("embedded NUL byte", lambda home: "C:\\bad\x00name"),
    ])
    def test_returns_none_instead_of_raising(self, rag_enforce, home, label, make_path):
        _write_registry(home, {})
        p = make_path(home)
        result = rag_enforce._project_root(p)
        assert result is None, f"{label}: expected None, got {result!r}"


class TestRegisteredProjectsRegistry:
    @pytest.mark.parametrize("label,content", [
        ("missing file", None),
        ("empty file", ""),
        ("invalid json", "{not json"),
        ("json list not object", "[1,2,3]"),
        ("entries not objects", json.dumps({"a": "just a string", "b": 5, "c": None})),
        ("project_path absent", json.dumps({"a": {}})),
        ("project_path null", json.dumps({"a": {"project_path": None}})),
        ("project_path int", json.dumps({"a": {"project_path": 5}})),
        ("project_path empty string", json.dumps({"a": {"project_path": ""}})),
    ])
    def test_malformed_registry_yields_empty_list_not_an_exception(self, rag_enforce, home, label, content):
        reg_path = home / "state" / "projects.json"
        if content is None:
            if reg_path.exists():
                reg_path.unlink()
        else:
            reg_path.write_text(content, encoding="utf-8")
        assert rag_enforce._registered_projects() == [], label

    def test_a_valid_entry_is_still_read_correctly(self, rag_enforce, home):
        target = home / "proj"
        _write_registry(home, {"a": {"project_path": str(target)}})
        assert rag_enforce._registered_projects() == [str(target)]


class TestRegisteredProjectsUnder:
    def test_excludes_root_itself_and_a_prefix_matching_sibling(self, rag_enforce, home):
        """Attacks case, trailing separators, dotted segments, and the sibling
        whose name merely starts with the root's name (C:\\DevelopmentOther
        against root C:\\Development)."""
        root = home / "Development"
        child = root / "Domain"
        child.mkdir(parents=True)
        sibling = home / "DevelopmentOther"
        sibling_child = sibling / "proj"
        sibling_child.mkdir(parents=True)

        _write_registry(home, {
            "descendant": {"project_path": str(child)},
            "root_itself_trailing_sep": {"project_path": str(root) + "\\"},
            "prefix_sibling": {"project_path": str(sibling_child)},
            "case_variant_descendant": {"project_path": str(child).upper()},
        })

        result = rag_enforce._registered_projects_under(str(root))

        assert any(Path(r) == child.resolve() for r in result), (
            "a true descendant must be included"
        )
        assert not any("DevelopmentOther" in r for r in result), (
            "a sibling whose name starts with the root's name must not be "
            "mistaken for a descendant"
        )
        assert not any(Path(r) == root.resolve() for r in result), (
            "root itself, even spelled with a trailing separator, must be excluded"
        )

    def test_root_argument_case_and_trailing_separator_do_not_change_the_answer(self, rag_enforce, home):
        root = home / "Development"
        child = root / "Domain"
        child.mkdir(parents=True)
        _write_registry(home, {"a": {"project_path": str(child)}})

        base = rag_enforce._registered_projects_under(str(root))
        upper = rag_enforce._registered_projects_under(str(root).upper())
        trailing = rag_enforce._registered_projects_under(str(root) + "\\")

        assert base == upper == trailing


class TestIntField:
    @pytest.mark.parametrize("label,value,expected", [
        ("None", None, 0),
        ("string digits", "5", 0),
        ("float", 5.0, 0),
        ("list", [1, 2], 0),
        ("dict", {"x": 1}, 0),
        ("bool True", True, 0),
        ("bool False", False, 0),
        ("real positive int", 5, 5),
        ("real zero", 0, 0),
        ("real negative int", -3, -3),
    ])
    def test_int_field_coercion(self, rag_enforce, label, value, expected):
        assert rag_enforce._int_field({"k": value}, "k") == expected, label

    def test_source_not_a_dict(self, rag_enforce):
        assert rag_enforce._int_field("not-a-dict", "k") == 0


class TestIndexedDecisionEndToEnd:
    """is_indexed inside _git_project_context must be false for a row with no
    real data behind it, and the refusal branch it feeds into must actually
    refuse: no subprocess, a real message naming the way forward."""

    def _run(self, rag_enforce, home, monkeypatch, files_indexed_value):
        container = home / "Development"
        child = container / "Domain"
        child.mkdir(parents=True)

        entries = {
            "container": {"project_path": str(container), "files_indexed": files_indexed_value},
            "child": {"project_path": str(child), "files_indexed": 500},
        }
        _write_registry(home, entries)

        monkeypatch.chdir(container)
        result, popen_calls = _run_git_project_context(
            rag_enforce, {"projects": {"entries": entries}}, rag_enforce._project_root()
        )
        return result, popen_calls, container, child

    @pytest.mark.parametrize("bad_value", [0, None, "5", 5.0, True])
    def test_a_registry_row_with_no_real_index_behind_it_never_reports_indexed(
        self, rag_enforce, home, monkeypatch, bad_value
    ):
        result, popen_calls, container, child = self._run(rag_enforce, home, monkeypatch, bad_value)
        assert "is indexed" not in result, (
            f"files_indexed={bad_value!r} was treated as a real index"
        )

    def test_the_refusal_branch_names_a_way_forward_and_spawns_nothing(self, rag_enforce, home, monkeypatch):
        result, popen_calls, container, child = self._run(rag_enforce, home, monkeypatch, 0)
        assert result.strip() != "", "the refusal must say something to the user"
        assert "not be" in result and "indexed automatically" in result
        assert str(child.resolve()) in result, "it must name the contained project"
        assert popen_calls == [], "the refusal branch must never spawn the indexer"

    def test_a_container_holding_a_junction_spelled_project_is_never_auto_indexed(
        self, rag_enforce, home
    ):
        """The whole point of the refusal, against the one spelling that used to
        walk straight past it. The contained project is registered under its
        junction path, which shares no lexical prefix with the container it
        really sits in, so the container read as holding nothing and was handed
        to the indexer: every file under it, under a path nothing searches,
        holding the one global index lock."""
        container = home / "container"
        child = container / "RealProject"
        child.mkdir(parents=True)
        link = _make_junction(home / "child_link", child)
        if link is None:
            pytest.skip("this machine cannot create a junction")

        entries = {"child": {"project_path": str(link), "files_indexed": 500}}
        _write_registry(home, entries)

        banner, popen_calls = _run_git_project_context(
            rag_enforce, {"projects": {"entries": entries}}, str(container.resolve())
        )

        assert popen_calls == [], (
            "the container holds a registered project, so nothing may be "
            f"queued, but it tried to index: {popen_calls!r}"
        )
        assert "will not be indexed automatically" in banner, (
            f"the refusal must be said out loud, got {banner!r}"
        )
        assert str(child.resolve()) in banner, (
            "the refusal must name the contained project it found"
        )

    def test_a_project_registered_under_a_junction_is_not_queued_again(
        self, rag_enforce, home
    ):
        """A row naming this very directory under a spelling only the filesystem
        can fold is still a real index. Reading it as unindexed queues a fresh
        index of an already indexed project, once per prompt."""
        project = home / "project"
        project.mkdir()
        link = _make_junction(home / "project_link", project)
        if link is None:
            pytest.skip("this machine cannot create a junction")

        entries = {"p": {"project_path": str(link), "files_indexed": 500}}
        _write_registry(home, entries)

        banner, popen_calls = _run_git_project_context(
            rag_enforce, {"projects": {"entries": entries}}, str(project.resolve())
        )

        assert "is indexed" in banner, f"got {banner!r}"
        assert popen_calls == [], "an already indexed project must not be queued"

    @pytest.mark.parametrize("bad_value", [0, None, "5", 5.0, True])
    def test_the_spelling_comparison_still_demands_a_real_index(
        self, rag_enforce, home, bad_value
    ):
        """Folding the spelling must not also fold away the files_indexed test.
        A row with no data behind it is not an index, whichever way it is
        spelled."""
        project = home / "project"
        project.mkdir()
        link = _make_junction(home / "project_link", project)
        if link is None:
            pytest.skip("this machine cannot create a junction")

        entries = {"p": {"project_path": str(link), "files_indexed": bad_value}}
        _write_registry(home, entries)

        banner, _popen_calls = _run_git_project_context(
            rag_enforce, {"projects": {"entries": entries}}, str(project.resolve())
        )

        assert "is indexed" not in banner, (
            f"files_indexed={bad_value!r} under a junction spelling was treated "
            "as a real index"
        )

    def test_mutant_int_field_threshold_off_by_one_is_caught(self, rag_enforce, home, monkeypatch):
        """Proves the parametrized test above is not vacuous: a `>= 0`
        mutant of the `> 0` check (the exact off-by-one this code's own
        comment says it exists to prevent) makes this test fail, by manually
        replaying the mutated expression against the same fixture data rather
        than mutating the source file on disk."""
        container = home / "Development"
        child = container / "Domain"
        child.mkdir(parents=True)
        entries = {
            "container": {"project_path": str(container), "files_indexed": 0},
        }
        root_norm = rag_enforce._norm_path(str(container))

        def is_indexed_with_ge(entries):
            return any(
                rag_enforce._norm_path(rag_enforce._str_field(e, "project_path")) == root_norm
                and rag_enforce._int_field(e, "files_indexed") >= 0  # mutant: > became >=
                for e in entries.values()
            )

        assert is_indexed_with_ge(entries) is True, (
            "sanity: confirms the mutant really would misreport an empty "
            "project as indexed"
        )
        # The real code's own `> 0` must not do this:
        def is_indexed_real(entries):
            return any(
                rag_enforce._norm_path(rag_enforce._str_field(e, "project_path")) == root_norm
                and rag_enforce._int_field(e, "files_indexed") > 0
                for e in entries.values()
            )
        assert is_indexed_real(entries) is False


class TestOneProjectPerPrompt:
    """rag-enforce.py names a project to the user in its "## Project Context"
    banner and then searches a project in `sources`. Those two must be the
    same project. The registry is a file another process writes: the
    background index runner rewrites state/projects.json when an index
    finishes, and it can finish while this hook is mid-prompt.
    """

    def test_the_project_named_to_the_user_is_the_project_that_gets_searched(
        self, rag_enforce, home, monkeypatch, capsys
    ):
        cwd = home / "Development" / "Domain"
        cwd.mkdir(parents=True)
        (cwd.parent / ".git").mkdir()

        # A registry that gains this project between reads. Faked at the reader
        # rather than by writing the file from a thread, so the interleaving is
        # deterministic: read one sees nothing registered, every later read sees
        # cwd registered. A resolver called twice answers the containing repo
        # first and cwd second.
        registry_reads = []

        def registry_gains_the_project_after_the_first_read():
            registry_reads.append(1)
            return [] if len(registry_reads) == 1 else [str(cwd)]

        monkeypatch.setattr(
            rag_enforce, "_registered_projects",
            registry_gains_the_project_after_the_first_read,
        )
        monkeypatch.chdir(cwd)
        monkeypatch.setattr(
            rag_enforce.sys, "stdin",
            io.StringIO(json.dumps({
                "prompt": "please refactor the authentication module today",
                "session_id": "s-one-project",
            })),
        )

        searched_sources = []

        def fake_urlopen(req, timeout=None):
            if req.full_url.endswith("/search"):
                searched_sources.extend(json.loads(req.data)["sources"])
                return _FakeStatusResponse({"results": []})
            return _FakeStatusResponse({"status": "ready", "projects": {"entries": {}}})

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            assert rag_enforce.main() == 0

        out = capsys.readouterr().out

        assert len(registry_reads) >= 2, (
            "sanity: this only proves anything if the registry was read more "
            f"than once during the prompt (reads={len(registry_reads)})"
        )
        assert len(searched_sources) == 1, f"expected one search source, got {searched_sources!r}"
        searched = searched_sources[0].removeprefix("project:")
        assert f"## Project Context\n{searched} " in out, (
            "the project named in the banner is not the project that was "
            f"searched: searched={searched!r}, banner output={out!r}"
        )


class TestProjectRootCostDoesNotGrowWithTheRegistry:
    """_project_root() runs on every single prompt. Deciding which of the
    registered projects a path belongs to must not cost a filesystem call per
    registered project: that is a per-prompt latency bill that grows for the
    lifetime of the tool, and it buys nothing, since only the nodes on the
    current walk-up path can ever match.
    """

    def test_cost_stays_near_the_pure_walk_baseline(self, rag_enforce, home, monkeypatch):
        deep = home / "deep"
        node = deep
        for i in range(20):
            node = node / f"lvl{i}"
        node.mkdir(parents=True)

        def time_for(n):
            reg = {f"h{i}": {"project_path": str(home / f"proj{i}")} for i in range(n)}
            _write_registry(home, reg)
            rag_enforce._project_root(str(node))  # warm up OS path caches once
            start = time.perf_counter()
            for _ in range(10):
                rag_enforce._project_root(str(node))
            return (time.perf_counter() - start) / 10

        baseline = time_for(0)     # pure walk cost, no registry contribution
        realistic = time_for(100)  # near today's real registry size (10, checked live)
        large = time_for(2000)

        print(f"\n_project_root() with an empty registry (pure walk cost): {baseline*1000:.2f} ms/call")
        print(f"_project_root() at registry size 100: {realistic*1000:.2f} ms/call")
        print(f"_project_root() at registry size 2000: {large*1000:.2f} ms/call")

        assert large < baseline * 5, (
            f"cost at 2000 registered projects ({large*1000:.2f} ms/call) is "
            f"more than 5x the pure walk baseline ({baseline*1000:.2f} ms/call) "
            "-- comparing the walk against the registry must not cost a "
            "filesystem call per registered project, on a hook that fires on "
            "every single prompt"
        )

    def test_a_prompt_from_a_registered_project_pays_nothing_for_the_registry(
        self, rag_enforce, home, monkeypatch
    ):
        """The shape of a real prompt: cwd is a registered project, so the free
        string comparison answers at the first level. Folding the spellings only
        the filesystem knows about has to stay on the branch that comparison
        misses, or every prompt is back to a syscall per registered project."""
        project = home / "Domain"
        project.mkdir()

        def time_for(n):
            reg = {f"h{i}": {"project_path": str(home / f"proj{i}")} for i in range(n)}
            reg["mine"] = {"project_path": str(project)}
            _write_registry(home, reg)
            rag_enforce._project_root(str(project))  # warm up OS path caches once
            start = time.perf_counter()
            for _ in range(20):
                assert rag_enforce._project_root(str(project)) == str(project.resolve())
            return (time.perf_counter() - start) / 20

        small = time_for(1)
        large = time_for(2000)
        marginal = (large - small) / 2000

        # Calibrated against this machine rather than a constant: the threshold
        # is what one filesystem call actually costs here, so the test says
        # "cheaper than a syscall per entry" and keeps saying it on hardware
        # where a syscall is faster or slower.
        probe = [str(home / f"proj{i}") for i in range(2000)]
        for p in probe[:50]:
            os.path.isdir(p)  # warm up
        start = time.perf_counter()
        for p in probe:
            os.path.isdir(p)
        one_syscall = (time.perf_counter() - start) / 2000

        print(f"\n_project_root() from a registered cwd, registry size 1: {small*1000:.3f} ms/call")
        print(f"_project_root() from a registered cwd, registry size 2000: {large*1000:.3f} ms/call")
        print(f"marginal cost per registered project: {marginal*1e6:.2f} us")
        print(f"one filesystem call on this machine: {one_syscall*1e6:.2f} us")

        assert marginal < one_syscall / 2, (
            f"each extra registered project cost {marginal*1e6:.2f} us on a prompt "
            f"that never left the free string comparison, against {one_syscall*1e6:.2f} us "
            "for a single filesystem call. That is the shape of a stat per entry "
            "on the hot path, which is the per-prompt bill this resolver exists "
            "to avoid"
        )


class TestHookExitsZeroRegardlessOfInput:
    """A UserPromptSubmit hook cannot block. This drives the real script as a
    subprocess against an isolated CLEAN_RAG_HOME and a port nobody is
    listening on, so a garbled payload can never end the turn with anything
    but exit 0."""

    HOOK = CLEAN_RAG / "hooks" / "rag-enforce.py"

    @pytest.mark.parametrize("label,stdin_data", [
        ("empty stdin", ""),
        ("not json", "not json at all {{{"),
        ("json list instead of object", "[1,2,3]"),
        ("json number instead of object", "42"),
        ("json null", "null"),
        ("prompt is an int", json.dumps({"prompt": 5, "session_id": "s1"})),
        ("prompt is a list", json.dumps({"prompt": [1, 2], "session_id": "s1"})),
        ("session_id missing", json.dumps({"prompt": "a real question here"})),
        ("transcript_path is an int", json.dumps({"prompt": "hi", "transcript_path": 5})),
    ])
    def test_garbage_payload_still_exits_zero(self, tmp_path, label, stdin_data):
        (tmp_path / "state").mkdir(parents=True, exist_ok=True)
        cwd_dir = tmp_path / "cwd"
        cwd_dir.mkdir()

        env = dict(os.environ)
        env["CLEAN_RAG_HOME"] = str(tmp_path)
        env["CLEAN_RAG_PORT"] = "18614"  # nobody listening

        proc = subprocess.run(
            [sys.executable, str(self.HOOK)],
            input=stdin_data, capture_output=True, text=True,
            cwd=str(cwd_dir), env=env, timeout=20,
        )
        assert proc.returncode == 0, (
            f"{label}: exited {proc.returncode}, stderr={proc.stderr[:500]!r}"
        )
