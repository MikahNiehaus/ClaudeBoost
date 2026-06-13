"""
pytest fixtures for ClaudeBoost hook tests.

Shared utilities live in helpers.py — import from there, not here.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

# Make scripts/tests/ importable so test files can do `from helpers import ...`
sys.path.insert(0, str(Path(__file__).parent))

TESTS_DIR = Path(__file__).resolve().parent


def pytest_configure(config):
    # Prepend tests dir to PYTHONPATH so subprocess-invoked scripts
    # pick up sitecustomize.py and start coverage automatically.
    tests_dir_str = str(TESTS_DIR)
    existing = os.environ.get("PYTHONPATH", "")
    if tests_dir_str not in existing:
        os.environ["PYTHONPATH"] = tests_dir_str + (os.pathsep + existing if existing else "")


@pytest.fixture()
def boost_home(tmp_path: Path) -> Path:
    """Temp CLAUDEBOOST_HOME with a state/ subdirectory."""
    home = tmp_path / "claudeboost"
    (home / "state").mkdir(parents=True)
    return home


@pytest.fixture()
def rag_live(tmp_path: Path) -> dict:
    """Env dict that makes _rag_is_live() return True (fresh heartbeat)."""
    rag_index_dir = tmp_path / "rag-index"
    rag_index_dir.mkdir()
    heartbeat = rag_index_dir / ".heartbeat"
    heartbeat.write_text(json.dumps({"ts": time.time()}), encoding="utf-8")
    return {"RAG_INDEX_DIR": str(rag_index_dir)}


@pytest.fixture()
def rag_dead(tmp_path: Path) -> dict:
    """Env dict that makes _rag_is_live() return False (no heartbeat).

    Must point at a real-but-empty location, not "": the guard treats an
    empty RAG_INDEX_DIR as unset and falls back to the repo's own
    .rag-index. On macOS that fallback resolves whenever the dev server is
    running, so the test would block instead of failing open.
    """
    return {"RAG_INDEX_DIR": str(tmp_path / "no-rag-index"), "LOCALAPPDATA": ""}
