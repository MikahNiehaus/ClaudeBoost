"""Tests for the three reliability fixes that keep a long reindex finishing.

Each one is tied to a real observed failure, not a hypothetical:
  * a healthy 907 file project reached 98 of 200 pauses while progressing,
  * one non UTF8 file logged the identical decode error on 98 straight passes
    and was never indexed,
  * the job exits 75 for memory and nothing was listening for it.
"""

import json
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server.file_scan import looks_binary, scan_project  # noqa: E402
from server.indexing import UNREADABLE_SENTINEL, file_hash  # noqa: E402


class TestBinarySniff:
    def test_a_nul_byte_makes_it_binary(self, tmp_path):
        f = tmp_path / "log.txt"
        f.write_bytes(b"readable text\x00then binary")
        assert looks_binary(f) is True

    def test_plain_source_is_not_binary(self, tmp_path):
        f = tmp_path / "a.py"
        f.write_text("def f():\n    return 1\n", encoding="utf-8")
        assert looks_binary(f) is False

    def test_utf8_multibyte_is_not_binary(self, tmp_path):
        """Accented names and emoji in comments are normal source, not binary."""
        f = tmp_path / "a.py"
        f.write_text("# café — \U0001f600\nx = 1\n", encoding="utf-8")
        assert looks_binary(f) is False

    def test_empty_file_is_not_binary(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_bytes(b"")
        assert looks_binary(f) is False

    def test_a_nul_past_the_sniff_window_is_missed_and_that_is_ok(self, tmp_path):
        """Documents the bound honestly. The manifest sentinel is the backstop
        for anything the sniff does not catch."""
        f = tmp_path / "big.txt"
        f.write_bytes(b"a" * 20000 + b"\x00")
        assert looks_binary(f) is False

    def test_unopenable_file_is_not_treated_as_binary(self, tmp_path):
        """Err toward keeping it: a file we cannot open should be reported
        properly by the indexer, not silently dropped from the scan."""
        assert looks_binary(tmp_path / "does-not-exist.py") is False

    def test_scan_project_excludes_a_binary_dot_txt(self, tmp_path):
        """.txt is in CODE_EXTENSIONS, so only a content check catches this.
        This is the exact shape of the file that looped 98 times."""
        good = tmp_path / "notes.txt"
        good.write_text("plain notes\n", encoding="utf-8")
        bad = tmp_path / "run_log.txt"
        bad.write_bytes(b"start\x97\x00\xfe binary junk")

        found = {Path(p).name for p in scan_project(str(tmp_path))}
        assert "notes.txt" in found
        assert "run_log.txt" not in found


class TestUnreadableSentinel:
    def test_sentinel_cannot_collide_with_a_real_hash(self):
        """file_hash is exactly 16 lowercase hex chars, so a non hex string is
        collision proof by construction."""
        h = file_hash("anything at all")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)
        assert UNREADABLE_SENTINEL != h
        assert not all(c in "0123456789abcdef" for c in UNREADABLE_SENTINEL)

    def test_find_changed_files_skips_a_sentinel_entry(self, tmp_path, monkeypatch):
        """The loop that logged the same error 98 times.

        find_changed_files reads with errors="replace" so it always succeeds,
        and would hash the replacement characters, mismatch the sentinel, and
        offer the file back to an indexer that refuses it every time.
        """
        import server.auto_reindex as ar

        project = tmp_path / "proj"
        project.mkdir()
        bad = project / "run_log.txt"
        bad.write_bytes(b"text\x97more")  # decodes only with errors="replace"
        ok = project / "fine.py"
        ok.write_text("x = 1\n", encoding="utf-8")

        index_dir = tmp_path / "idx"
        index_dir.mkdir()
        manifest = index_dir / "manifest.json"
        manifest.write_text(json.dumps({
            "__project_path__": str(project),
            "run_log.txt": UNREADABLE_SENTINEL,
            "fine.py": file_hash("x = 1\n"),
        }), encoding="utf-8")

        monkeypatch.setattr(
            ar, "_project_paths",
            lambda p: (project, "pid", index_dir, index_dir / "chroma", manifest),
        )
        # The real scan would drop the binary file; force it through so this
        # test proves the manifest check, not the sniff.
        monkeypatch.setattr(ar, "scan_project", lambda p: [str(bad), str(ok)])

        changed, deleted = ar.find_changed_files(str(project))
        assert str(bad) not in changed, (
            "a known unreadable file was offered for reindexing again"
        )
        assert changed == []
        assert deleted == []

    def test_a_genuinely_changed_file_is_still_detected(self, tmp_path, monkeypatch):
        """The guard must not suppress real work."""
        import server.auto_reindex as ar

        project = tmp_path / "proj"
        project.mkdir()
        f = project / "a.py"
        f.write_text("x = 2\n", encoding="utf-8")

        index_dir = tmp_path / "idx"
        index_dir.mkdir()
        manifest = index_dir / "manifest.json"
        manifest.write_text(json.dumps({
            "__project_path__": str(project),
            "a.py": file_hash("x = 1\n"),  # stale
        }), encoding="utf-8")

        monkeypatch.setattr(
            ar, "_project_paths",
            lambda p: (project, "pid", index_dir, index_dir / "chroma", manifest),
        )
        monkeypatch.setattr(ar, "scan_project", lambda p: [str(f)])

        changed, _deleted = ar.find_changed_files(str(project))
        assert str(f) in changed


class TestStallBudget:
    """A pause that indexed files is progress, not a stall."""

    def _batch(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "reindex_batch_stall_test", CLEAN_RAG / "cli" / "reindex_batch.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_outer_cap_is_high_enough_for_the_largest_real_project(self):
        """Nectar is 4492 files at an observed 3 to 30 files per pause, so
        roughly 900 cycles. The old cap of 200 would have abandoned it."""
        b = self._batch()
        assert b.MAX_PAUSES_PER_PROJECT >= 1000, (
            f"outer cap {b.MAX_PAUSES_PER_PROJECT} would abandon a large "
            f"project that is progressing normally"
        )

    def test_stall_budget_is_tight(self):
        """Making no progress repeatedly means something is wrong, so this one
        should fire quickly."""
        b = self._batch()
        assert 1 < b.MAX_STALLED_PAUSES <= 100

    def test_the_two_budgets_are_distinct(self):
        b = self._batch()
        assert b.MAX_STALLED_PAUSES < b.MAX_PAUSES_PER_PROJECT

    @pytest.mark.parametrize(
        "progress_sequence,expect_stalled",
        [
            ([5, 5, 5, 5, 5], 0),        # steady progress: never stalls
            ([0, 0, 0], 3),              # nothing at all: counts up
            ([0, 0, 4, 0], 1),           # progress resets it
            ([1, 0, 1, 0, 1, 0], 1),     # alternating: reset each time
        ],
    )
    def test_reset_semantics(self, progress_sequence, expect_stalled):
        """The counter logic itself, isolated from the loop.

        The alternating case is the one swiper warned about: any progress
        resets, so a project doing one file per cycle never trips the stall
        budget. That is why the outer cap stays.
        """
        stalled = 0
        for indexed in progress_sequence:
            stalled = 0 if indexed > 0 else stalled + 1
        assert stalled == expect_stalled

    def test_no_supervisor_is_documented_rather_than_built(self):
        """A previous wrapper was written and deleted. The docstring must say
        what to do instead, or the exit code is a dead end at 3am."""
        source = (CLEAN_RAG / "cli" / "reindex_batch.py").read_text(encoding="utf-8")
        assert "run the same command again" in source.lower()
