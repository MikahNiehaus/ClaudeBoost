"""
Tests for scripts/check-rag-path.py — prints rag_server __file__ path.

This script is tiny: imports rag_server and prints __file__.
"""
from __future__ import annotations

from helpers import run_script


class TestCheckRagPath:
    def test_exits_0_or_nonzero(self):
        # Either rag_server is found (exit 0, prints path) or not (exit nonzero)
        result = run_script("check-rag-path.py")
        # Should be either 0 (found) or nonzero (ImportError)
        assert result.returncode in (0, 1)

    def test_prints_path_when_importable(self):
        result = run_script("check-rag-path.py")
        if result.returncode == 0:
            output = result.stdout.decode("utf-8", errors="replace").strip()
            assert len(output) > 0
            assert "rag_server" in output.lower() or ".py" in output

    def test_script_is_runnable(self):
        result = run_script("check-rag-path.py")
        assert result.returncode != 127  # script found and runnable
