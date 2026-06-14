"""
Tests for scripts/rag-agent-guard.py (PreToolUse hook on Agent).

NOTE: rag-agent-guard.py was removed from the codebase. These tests are skipped.

The guard checks heartbeat age before allowing agent spawns.
Always exits 0 (fail-open) — warns on stale heartbeat but never blocks.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from helpers import run_hook, pretooluse

pytestmark = pytest.mark.skip(reason="rag-agent-guard.py was removed from the codebase")


def _spawn(description: str = "do some task") -> dict:
    return pretooluse("Task", {
        "description": description,
        "prompt": "perform the task",
        "subagent_type": "general-purpose",
    })


class TestHeartbeatFresh:
    def test_allows_when_heartbeat_is_fresh(self, rag_live):
        result = run_hook("rag-agent-guard.py", _spawn(), env_overrides=rag_live)
        assert result.returncode == 0

    def test_no_warning_on_fresh_heartbeat(self, rag_live):
        result = run_hook("rag-agent-guard.py", _spawn(), env_overrides=rag_live)
        assert result.returncode == 0
        assert result.stderr == b""


class TestHeartbeatMissing:
    def test_allows_when_heartbeat_missing(self, rag_dead):
        result = run_hook("rag-agent-guard.py", _spawn(), env_overrides=rag_dead)
        # Fail-open: missing heartbeat still allows
        assert result.returncode == 0


class TestHeartbeatStale:
    def test_allows_but_warns_on_stale_heartbeat(self, tmp_path):
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        # Write a timestamp from 3 minutes ago (well past the 90s threshold)
        old_ts = time.time() - 180
        heartbeat.write_text(json.dumps({"ts": old_ts}), encoding="utf-8")

        result = run_hook(
            "rag-agent-guard.py",
            _spawn(),
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0
        # Stale heartbeat → warning on stderr
        assert b"WARNING" in result.stderr or b"stale" in result.stderr.lower()

    def test_plain_ts_float_in_json_object_stale(self, tmp_path):
        """Heartbeat as JSON object with ts key — standard format, stale timestamp."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        # Use JSON object format (what the server actually writes)
        heartbeat.write_text(json.dumps({"ts": time.time() - 200, "model_loaded": True}), encoding="utf-8")

        result = run_hook(
            "rag-agent-guard.py",
            _spawn(),
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0
        assert b"WARNING" in result.stderr or b"stale" in result.stderr.lower()

    def test_plain_float_heartbeat_format_stale(self, tmp_path):
        """Plain float heartbeat triggers AttributeError on .get() — outer except returns None, fail-open."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        # json.loads("1749805000.123") succeeds as a JSON number float, then .get("ts") raises
        # AttributeError (not caught by inner except), propagates to outer except: return None.
        # _heartbeat_age() returns None → fail-open, no warning.
        heartbeat.write_text(str(time.time() - 200), encoding="utf-8")

        result = run_hook(
            "rag-agent-guard.py",
            _spawn(),
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0
        # No warning: age is None (outer exception), not stale
        assert result.stderr == b""

    def test_corrupt_heartbeat_returns_none(self, tmp_path):
        """Corrupt heartbeat content that can't be parsed at all — allow spawn (fail-open)."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        heartbeat.write_text("not-a-number-or-json", encoding="utf-8")

        result = run_hook(
            "rag-agent-guard.py",
            _spawn(),
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0


class TestNoEnvVarsSet:
    def test_allows_when_no_rag_index_dir_or_localappdata(self):
        """Both RAG_INDEX_DIR and LOCALAPPDATA unset — uses macOS/Linux fallback path, fail-open."""
        result = run_hook(
            "rag-agent-guard.py",
            _spawn(),
            env_overrides={"RAG_INDEX_DIR": "", "LOCALAPPDATA": ""},
        )
        assert result.returncode == 0

    def test_allows_when_localappdata_set_but_no_rag_index_dir(self, tmp_path):
        """LOCALAPPDATA set, RAG_INDEX_DIR not set — uses Windows fallback, no heartbeat → fail-open."""
        result = run_hook(
            "rag-agent-guard.py",
            _spawn(),
            env_overrides={"RAG_INDEX_DIR": "", "LOCALAPPDATA": str(tmp_path)},
        )
        assert result.returncode == 0
