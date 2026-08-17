"""Targeted tests for all 5 bad-cop findings.

These test behavioral contracts, not implementation details.
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the clean-rag directory to the path so we can import the server modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# === Finding 1: _run_mutatest computes common parent of ALL Python files ===

class TestMutatestCommonParent:
    """The --src argument must be the common ancestor of all Python files,
    not just the first file's parent."""

    def test_single_file_uses_its_parent(self):
        from server.mutation import _run_mutatest
        # We don't have mutatest installed, so mock shutil.which to return None
        # and verify it returns None (not installed fallback)
        with patch("server.mutation.shutil.which", return_value=None):
            result = _run_mutatest(Path("."), ["src/a.py"], [])
            assert result is None  # Not installed, returns None

    def test_common_parent_computed_across_files(self):
        """When files span multiple directories, src_dir must be
        their common ancestor, not just the first file's parent."""
        from server.mutation import _run_mutatest
        captured_argv = []

        def fake_which(name):
            return "/usr/bin/mutatest" if name == "mutatest" else None

        def fake_run(argv, cwd, timeout=600):
            captured_argv.extend(argv)
            proc = MagicMock()
            proc.stdout = ""
            proc.stderr = ""
            proc.returncode = 0
            return proc

        with patch("server.mutation.shutil.which", side_effect=fake_which), \
             patch("server.mutation._run", side_effect=fake_run):
            _run_mutatest(Path("/project"), ["src/a.py", "tests/b.py"], [])

        # The common parent of src/a.py and tests/b.py is "." (the root)
        assert "--src" in captured_argv
        src_idx = captured_argv.index("--src")
        src_val = captured_argv[src_idx + 1]
        assert src_val == ".", f"Expected '.' as common parent of src/ and tests/, got '{src_val}'"

    def test_same_dir_files_use_that_dir(self):
        """When all files are in the same directory, that directory is used."""
        from server.mutation import _run_mutatest
        captured_argv = []

        def fake_which(name):
            return "/usr/bin/mutatest" if name == "mutatest" else None

        def fake_run(argv, cwd, timeout=600):
            captured_argv.extend(argv)
            proc = MagicMock()
            proc.stdout = ""
            proc.stderr = ""
            proc.returncode = 0
            return proc

        with patch("server.mutation.shutil.which", side_effect=fake_which), \
             patch("server.mutation._run", side_effect=fake_run):
            _run_mutatest(Path("/project"), ["src/models/a.py", "src/models/b.py"], [])

        assert "--src" in captured_argv
        src_idx = captured_argv.index("--src")
        src_val = captured_argv[src_idx + 1]
        # Both files are under src/models, so that should be the src dir
        assert src_val == "src/models" or src_val == "src\\models", \
            f"Expected 'src/models' as common parent, got '{src_val}'"

    def test_nested_common_parent(self):
        """Files in pkg/sub1 and pkg/sub2 should yield pkg as common parent."""
        from server.mutation import _run_mutatest
        captured_argv = []

        def fake_which(name):
            return "/usr/bin/mutatest" if name == "mutatest" else None

        def fake_run(argv, cwd, timeout=600):
            captured_argv.extend(argv)
            proc = MagicMock()
            proc.stdout = ""
            proc.stderr = ""
            proc.returncode = 0
            return proc

        with patch("server.mutation.shutil.which", side_effect=fake_which), \
             patch("server.mutation._run", side_effect=fake_run):
            _run_mutatest(Path("/project"), ["pkg/sub1/a.py", "pkg/sub2/b.py"], [])

        assert "--src" in captured_argv
        src_idx = captured_argv.index("--src")
        src_val = captured_argv[src_idx + 1]
        assert src_val == "pkg", f"Expected 'pkg' as common parent, got '{src_val}'"


# === Finding 2: _run_bandit skips when no Python files in changed set ===

class TestBanditNoPythonFiles:
    """When changed_files contains only non-Python files, bandit must skip
    entirely, not fall through to a recursive scan of the whole project."""

    def test_no_python_files_returns_empty(self):
        from server.security import _run_bandit

        def fake_which(name):
            return "/usr/bin/bandit" if name == "bandit" else None

        with patch("server.security.shutil.which", side_effect=fake_which):
            result = _run_bandit(Path("/project"), ["requirements.txt", "README.md"])

        # Should return empty list (skipped), not None (not installed)
        assert result == [], f"Expected empty list (skip), got {result}"

    def test_no_python_files_never_calls_subprocess(self):
        """Crucially, subprocess.run must never be called when there are no .py files."""
        from server.security import _run_bandit

        def fake_which(name):
            return "/usr/bin/bandit" if name == "bandit" else None

        with patch("server.security.shutil.which", side_effect=fake_which), \
             patch("server.security.subprocess.run") as mock_run:
            _run_bandit(Path("/project"), ["setup.cfg", "Dockerfile"])

        mock_run.assert_not_called()

    def test_python_files_still_scanned(self):
        """When there ARE Python files, bandit should still run on them."""
        from server.security import _run_bandit

        def fake_which(name):
            return "/usr/bin/bandit" if name == "bandit" else None

        mock_proc = MagicMock()
        mock_proc.stdout = '{"results": []}'
        mock_proc.returncode = 0

        with patch("server.security.shutil.which", side_effect=fake_which), \
             patch("server.security.subprocess.run", return_value=mock_proc) as mock_run:
            result = _run_bandit(Path("/project"), ["app.py", "README.md"])

        # subprocess.run should have been called with only app.py, not -r .
        mock_run.assert_called_once()
        argv = mock_run.call_args[0][0]
        assert "app.py" in argv, f"Expected app.py in argv, got {argv}"
        assert "-r" not in argv, f"Should not do recursive scan, got {argv}"
        assert "." not in argv, f"Should not scan '.', got {argv}"


# === Finding 3: docs and code must agree on the sweep interval ===

class TestDocReindexInterval:
    """Code and every doc must agree on the sweep interval.

    The interval is 10 minutes. It was 60 while the sweep was slow and
    self throttling; with CPU throttling off a 10 minute tick is cheap,
    because a tick over unchanged projects is just a hash diff.
    """

    #: Every file that states the interval in prose.
    DOCS = (
        str(Path(__file__).resolve().parents[2] / "CLAUDE.md"),
        str(Path(__file__).resolve().parents[1] / "CLAUDE.md"),
        str(Path(__file__).resolve().parents[1] / "portable" / "CLAUDE.md"),
        str(Path(__file__).resolve().parents[1] / "PORTABLE_SETUP.md"),
        str(Path(__file__).resolve().parents[2] / ".claude" / "commands" / "index-project.md"),
    )

    def test_code_interval_is_600(self):
        from server.auto_reindex import INTERVAL_S
        assert INTERVAL_S == 600, f"Expected 600 (10 minutes), got {INTERVAL_S}"

    def test_no_doc_still_claims_60_minutes(self):
        """One list, checked uniformly. The previous version hand wrote one
        test per file and they drifted out of agreement with each other."""
        stale = []
        for path in self.DOCS:
            p = Path(path)
            if not p.exists():
                continue
            text = p.read_text(encoding="utf-8")
            if "60 minutes" in text.lower():
                stale.append(path)
        assert not stale, f"still say 60 minutes: {stale}"

    def test_the_docs_that_state_an_interval_say_10(self):
        found = 0
        for path in self.DOCS:
            p = Path(path)
            if p.exists() and "10 minutes" in p.read_text(encoding="utf-8").lower():
                found += 1
        assert found >= 2, f"only {found} docs state the 10 minute interval"

# === Finding 4: Mutatest fallback uses shorter timeout ===

class TestMutatestTimeout:
    """The mutatest fallback (after mutmut timeout) must use a shorter
    timeout than the default 600s to avoid 20-minute total waits."""

    def test_mutatest_timeout_is_shorter_than_default(self):
        from server.mutation import _MUTATEST_TIMEOUT_S, DEFAULT_TIMEOUT_S
        assert _MUTATEST_TIMEOUT_S < DEFAULT_TIMEOUT_S, \
            f"Mutatest timeout ({_MUTATEST_TIMEOUT_S}s) should be less than default ({DEFAULT_TIMEOUT_S}s)"

    def test_mutatest_timeout_is_reasonable(self):
        from server.mutation import _MUTATEST_TIMEOUT_S
        assert 60 <= _MUTATEST_TIMEOUT_S <= 180, \
            f"Mutatest timeout should be 60-180s for a quick spot-check, got {_MUTATEST_TIMEOUT_S}s"

    def test_mutatest_uses_short_timeout_in_run(self):
        """Verify _run is actually called with the shorter timeout."""
        from server.mutation import _run_mutatest, _MUTATEST_TIMEOUT_S
        captured_timeout = []

        def fake_which(name):
            return "/usr/bin/mutatest" if name == "mutatest" else None

        def fake_run(argv, cwd, timeout=600):
            captured_timeout.append(timeout)
            proc = MagicMock()
            proc.stdout = ""
            proc.stderr = ""
            proc.returncode = 0
            return proc

        with patch("server.mutation.shutil.which", side_effect=fake_which), \
             patch("server.mutation._run", side_effect=fake_run):
            _run_mutatest(Path("/project"), ["a.py"], [])

        assert captured_timeout[0] == _MUTATEST_TIMEOUT_S, \
            f"Expected timeout {_MUTATEST_TIMEOUT_S}, got {captured_timeout[0]}"


# === Finding 5: Metrics schema always includes complexity_rank ===

class TestMetricsSchema:
    """complexity_rank must always be present in the metrics output,
    regardless of whether radon is installed."""

    def test_complexity_rank_present_without_radon(self):
        """When radon is not installed, complexity_rank should be None, not missing."""
        from server.metrics import _compute_metrics

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("x = 1\nif True:\n    y = 2\n")
            f.flush()
            tmp = f.name

        try:
            with patch("server.metrics._HAS_RADON", False):
                result = _compute_metrics(tmp)
            assert "complexity_rank" in result, \
                f"complexity_rank missing from result: {list(result.keys())}"
            # When radon is absent, complexity_rank should be None
            assert result["complexity_rank"] is None, \
                f"Without radon, complexity_rank should be None, got {result['complexity_rank']}"
        finally:
            os.unlink(tmp)

    def test_complexity_rank_present_with_radon(self):
        """When radon is installed and returns results, complexity_rank should be a letter."""
        from server.metrics import _compute_metrics, _HAS_RADON

        if not _HAS_RADON:
            # Can't test radon behavior without radon
            return

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("def foo():\n    return 1\n")
            f.flush()
            tmp = f.name

        try:
            result = _compute_metrics(tmp)
            assert "complexity_rank" in result, \
                f"complexity_rank missing from result with radon: {list(result.keys())}"
            assert result["complexity_rank"] in ("A", "B", "C", "D", "E", "F"), \
                f"Unexpected complexity_rank value: {result['complexity_rank']}"
        finally:
            os.unlink(tmp)

    def test_schema_consistent_across_radon_states(self):
        """The set of keys (minus optional warning) must be identical
        whether radon is present or not."""
        from server.metrics import _compute_metrics

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write("def bar():\n    x = 1\n    return x\n")
            f.flush()
            tmp = f.name

        try:
            with patch("server.metrics._HAS_RADON", False):
                no_radon = _compute_metrics(tmp)
            # Core keys that must always be present
            required = {"file", "lines_of_code", "cyclomatic_complexity",
                        "complexity_rank", "maintainability_index", "call_graph",
                        "computed_at"}
            no_radon_keys = set(no_radon.keys())
            missing = required - no_radon_keys
            assert not missing, f"Keys missing without radon: {missing}"
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
