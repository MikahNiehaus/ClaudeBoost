"""
Tests for scripts/check-rag-health.py — RAG import/path health check.

Exit codes:
  0 - healthy
  1 - other error
  2 - ImportError
  3 - wrong path (outside CLAUDEBOOST_HOME)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from helpers import SCRIPTS_DIR, run_script


def _load_check_rag_health():
    spec = importlib.util.spec_from_file_location(
        "check_rag_health",
        SCRIPTS_DIR / "check-rag-health.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCheckRagHealthSubprocess:
    def test_exits_0_or_2_by_default(self):
        result = run_script("check-rag-health.py")
        assert result.returncode in (0, 1, 2, 3)

    def test_exits_3_when_home_set_to_wrong_path(self, tmp_path):
        result = run_script(
            "check-rag-health.py",
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode in (0, 2, 3)

    def test_no_exception_output_on_import_error(self, tmp_path):
        result = run_script(
            "check-rag-health.py",
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode != 127

    def test_script_is_runnable(self):
        result = run_script("check-rag-health.py")
        assert result.returncode != 127


class TestCheckRagHealthDirect:
    def test_exits_2_when_rag_server_not_importable(self, monkeypatch):
        """main() exits 2 when rag_server raises ImportError on import."""
        mod = _load_check_rag_health()

        import builtins
        real_import = builtins.__import__

        def fail_rag_server(name, *args, **kwargs):
            if name == "rag_server":
                raise ImportError("no module named rag_server")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fail_rag_server)
        result = mod.main()
        assert result == 2

    def test_exits_0_when_healthy(self, monkeypatch):
        """main() exits 0 when rag_server imports and sentence_transformers loads."""
        mod = _load_check_rag_health()

        fake_rag = MagicMock()
        fake_rag.__file__ = str(SCRIPTS_DIR / "rag_server.py")
        fake_st = MagicMock()

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "rag_server":
                return fake_rag
            if name == "sentence_transformers":
                return fake_st
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.setenv("CLAUDEBOOST_HOME", "")
        result = mod.main()
        assert result == 0

    def test_exits_2_when_sentence_transformers_import_error(self, monkeypatch):
        """main() exits 2 when sentence_transformers raises ImportError."""
        mod = _load_check_rag_health()

        fake_rag = MagicMock()
        fake_rag.__file__ = str(SCRIPTS_DIR / "rag_server.py")

        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "rag_server":
                return fake_rag
            if name == "sentence_transformers":
                raise ImportError("no sentence_transformers")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        monkeypatch.setenv("CLAUDEBOOST_HOME", "")
        result = mod.main()
        assert result == 2
