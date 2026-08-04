"""A file recorded unreadable must come back once it is repaired.

UNREADABLE_SENTINEL exists to stop an infinite retry: index_project reads
strictly and fails, find_changed_files reads with errors="replace" and
succeeds, so without the sentinel the two disagreed forever and one real
file logged the same UnicodeDecodeError on 98 consecutive passes.

The skip was unconditional though, which turned "stop retrying" into
"blacklist for life": proven end to end, a file repaired to valid UTF-8 was
still never offered by the hourly sweep, so it stayed missing from search
until someone ran a manual force=True rebuild. Both properties are asserted
here, because fixing either one alone recreates the other bug.
"""

import json
import logging
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

import server.auto_reindex as ar  # noqa: E402
from server.indexing import UNREADABLE_SENTINEL, file_hash  # noqa: E402

#: Lone continuation byte: passes looks_binary (no NUL) but cannot be decoded
#: as UTF-8, which is exactly the case the sentinel is recorded for.
UNDECODABLE = b"def g():\n    x = '\x93bad\x93'\n    return x\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project whose bad.py is already quarantined in the manifest."""
    root = tmp_path / "proj"
    root.mkdir()
    bad = root / "bad.py"
    bad.write_bytes(UNDECODABLE)
    good = root / "good.py"
    good.write_text("x = 1\n", encoding="utf-8")

    index_dir = tmp_path / "idx"
    index_dir.mkdir()
    manifest = index_dir / "manifest.json"
    manifest.write_text(json.dumps({
        "__project_path__": str(root),
        "bad.py": UNREADABLE_SENTINEL,
        "good.py": file_hash("x = 1\n"),
    }), encoding="utf-8")

    monkeypatch.setattr(
        ar, "_project_paths",
        lambda p: (root, "pid", index_dir, index_dir / "chroma", manifest),
    )
    monkeypatch.setattr(ar, "scan_project", lambda p: [str(bad), str(good)])
    return root, bad


class TestARepairedFileComesBack:
    def test_it_is_offered_after_being_fixed(self, project):
        """The finding: changed stayed [] forever after the repair."""
        root, bad = project
        bad.write_text("def g():\n    return 'fixed'\n", encoding="utf-8")

        changed, deleted = ar.find_changed_files(str(root))

        assert str(bad) in changed, (
            "a repaired file was never offered again; only a manual force "
            "rebuild could have recovered it"
        )
        assert deleted == []

    def test_lifting_the_quarantine_is_logged(self, project, caplog):
        root, bad = project
        bad.write_text("ok = True\n", encoding="utf-8")

        with caplog.at_level(logging.INFO, logger=ar.logger.name):
            ar.find_changed_files(str(root))

        assert any("quarantine lifted" in r.message.lower() for r in caplog.records), (
            f"no record of the recovery: {[r.message for r in caplog.records]}"
        )


class TestAnUnchangedBrokenFileIsStillNotRetried:
    def test_it_is_not_offered(self, project):
        """The original bug, which the sentinel exists to prevent. Rechecking
        readability must not become rechecking by handing it to the indexer.
        """
        root, bad = project

        changed, deleted = ar.find_changed_files(str(root))

        assert changed == [], (
            "a still undecodable file was offered back to an indexer that "
            "will refuse it again, which is the 98 pass retry loop"
        )
        assert deleted == []

    def test_it_stays_skipped_across_repeated_sweeps(self, project):
        root, _bad = project
        for _ in range(5):
            assert ar.find_changed_files(str(root))[0] == []

    def test_a_broken_file_that_changed_but_is_still_broken_is_not_offered(
        self, project
    ):
        """Editing a broken file into a differently broken one changes its
        bytes but not the answer to "can the indexer read it", so it must not
        wake the retry loop up."""
        root, bad = project
        bad.write_bytes(b"totally different \x81\x82 but still not utf-8\n")

        assert ar.find_changed_files(str(root))[0] == []

    def test_the_skip_leaves_a_trace(self, project, caplog):
        """A silent permanent skip is how a file goes missing from search with
        nothing to grep for."""
        root, _bad = project

        with caplog.at_level(logging.INFO, logger=ar.logger.name):
            ar.find_changed_files(str(root))

        messages = [r.getMessage() for r in caplog.records]
        assert any("unreadable" in m.lower() and "bad.py" in m for m in messages), (
            f"the skip left no trace: {messages}"
        )

    def test_the_trace_is_one_line_per_sweep_not_one_per_file(
        self, tmp_path, monkeypatch, caplog
    ):
        """Hourly, forever, for every quarantined file, is its own kind of
        unreadable."""
        root = tmp_path / "proj"
        root.mkdir()
        entries = {"__project_path__": str(root)}
        paths = []
        for i in range(12):
            f = root / f"bad{i}.py"
            f.write_bytes(UNDECODABLE)
            entries[f"bad{i}.py"] = UNREADABLE_SENTINEL
            paths.append(str(f))

        index_dir = tmp_path / "idx"
        index_dir.mkdir()
        manifest = index_dir / "manifest.json"
        manifest.write_text(json.dumps(entries), encoding="utf-8")
        monkeypatch.setattr(
            ar, "_project_paths",
            lambda p: (root, "pid", index_dir, index_dir / "chroma", manifest),
        )
        monkeypatch.setattr(ar, "scan_project", lambda p: paths)

        with caplog.at_level(logging.INFO, logger=ar.logger.name):
            ar.find_changed_files(str(root))

        unreadable_lines = [
            r for r in caplog.records if "unreadable" in r.getMessage().lower()
        ]
        assert len(unreadable_lines) == 1, (
            f"{len(unreadable_lines)} lines for 12 quarantined files"
        )
        assert "12" in unreadable_lines[0].getMessage()


class TestEndToEndThroughARealIndex:
    """Proves the two halves agree: what index_project records is what
    find_changed_files acts on."""

    class FakeEmbedder:
        """Not a ModelCache, so index_project takes the plain embedder path
        and never loads a real model."""
        model_name = "fake-test-model"

        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    def test_index_then_repair_then_sweep_recovers_the_file(
        self, tmp_path, monkeypatch
    ):
        from server import indexing

        monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
        # STATE_DIR too, or index_project's _update_project_registry writes this
        # throwaway tmp_path project into the REAL state/projects.json. That is
        # not hypothetical: seven pytest temp projects accumulated there and the
        # batch reindex then spent its time indexing directories that no longer
        # exist.
        state = tmp_path / "state"
        state.mkdir(exist_ok=True)
        monkeypatch.setattr(indexing, "STATE_DIR", state)

        root = tmp_path / "proj"
        root.mkdir()
        (root / "good.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        bad = root / "bad.py"
        bad.write_bytes(UNDECODABLE)

        result = indexing.index_project(str(root), self.FakeEmbedder(), force=True)
        assert result["files_failed"] == 1, result
        assert result["files_indexed"] == 1, result

        _root, _pid, _idx, _chroma, manifest_path = indexing._project_paths(str(root))
        recorded = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert recorded["bad.py"] == UNREADABLE_SENTINEL

        # Still broken: the sweep must leave it alone.
        assert ar.find_changed_files(str(root))[0] == []

        # Repaired: the sweep must pick it up, with no force rebuild involved.
        bad.write_text("def g():\n    return 'fixed'\n", encoding="utf-8")
        changed, _deleted = ar.find_changed_files(str(root))

        assert [Path(c).name for c in changed] == ["bad.py"], changed
