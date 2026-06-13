"""
Tests for scripts/rag-statusline.py (StatusLine script).

Outputs a colored status string to stdout. Never exits non-zero.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from helpers import run_script


class TestServerLive:
    def test_contains_rag_indicator_when_live(self, rag_live):
        result = run_script("rag-statusline.py", env_overrides=rag_live)
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "RAG" in output
        assert "●" in output

    def test_contains_cb_prefix_always(self, rag_live):
        result = run_script("rag-statusline.py", env_overrides=rag_live)
        output = result.stdout.decode(errors="replace")
        assert "CB" in output


class TestServerDown:
    def test_no_rag_indicator_when_server_down(self, rag_dead):
        result = run_script("rag-statusline.py", env_overrides=rag_dead)
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        # No RAG indicator when server is down
        assert "RAG ●" not in output

    def test_cb_prefix_still_shown_when_down(self, rag_dead):
        result = run_script("rag-statusline.py", env_overrides=rag_dead)
        output = result.stdout.decode(errors="replace")
        assert "CB" in output


class TestServerStarting:
    def test_starting_indicator_when_model_not_loaded(self, tmp_path):
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        heartbeat.write_text(json.dumps({"ts": time.time(), "model_loaded": False}), encoding="utf-8")

        result = run_script(
            "rag-statusline.py",
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        # Starting indicator (hollow circle)
        assert "○" in output or "RAG" in output


class TestStaleHeartbeat:
    def test_no_rag_indicator_when_heartbeat_stale(self, tmp_path):
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        heartbeat.write_text(json.dumps({"ts": time.time() - 200}), encoding="utf-8")

        result = run_script(
            "rag-statusline.py",
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "RAG ●" not in output


class TestHeartbeatFormats:
    def test_plain_float_heartbeat_shows_down(self, tmp_path):
        """Plain float heartbeat triggers AttributeError on .get() — outer except returns 'down'."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        # json.loads("1749805000.123") succeeds as JSON number, then .get("ts") raises
        # AttributeError → outer except: return "down". No RAG indicator.
        heartbeat.write_text(str(time.time()), encoding="utf-8")

        result = run_script("rag-statusline.py", env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)})
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "RAG ●" not in output

    def test_corrupt_heartbeat_shows_down(self, tmp_path):
        """Unreadable heartbeat content — outer except triggers, shows server as down."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        heartbeat = rag_index_dir / ".heartbeat"
        heartbeat.write_text('{"ts": "not-a-number"}', encoding="utf-8")

        result = run_script("rag-statusline.py", env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)})
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "RAG ●" not in output

    def test_localappdata_path_used_when_no_rag_index_dir(self, tmp_path):
        """LOCALAPPDATA set, RAG_INDEX_DIR not set — uses Windows fallback path."""
        result = run_script(
            "rag-statusline.py",
            env_overrides={"RAG_INDEX_DIR": "", "LOCALAPPDATA": str(tmp_path)},
        )
        assert result.returncode == 0
        assert "CB" in result.stdout.decode(errors="replace")

    def test_no_env_vars_uses_linux_fallback(self):
        """Neither RAG_INDEX_DIR nor LOCALAPPDATA set — uses macOS/Linux fallback path."""
        result = run_script(
            "rag-statusline.py",
            env_overrides={"RAG_INDEX_DIR": "", "LOCALAPPDATA": ""},
        )
        assert result.returncode == 0
        assert "CB" in result.stdout.decode(errors="replace")


class TestMcpRegistered:
    def test_no_claude_json_no_extra_indicators(self, tmp_path):
        """HOME has no .claude.json — no playwright/debugger indicators."""
        result = run_script(
            "rag-statusline.py",
            env_overrides={"RAG_INDEX_DIR": str(tmp_path), "USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "PW" not in output
        assert "DBG" not in output

    def test_corrupt_claude_json_no_crash(self, tmp_path):
        """Malformed .claude.json doesn't crash the statusline — exception silently ignored."""
        (tmp_path / ".claude.json").write_text("not valid json", encoding="utf-8")
        result = run_script(
            "rag-statusline.py",
            env_overrides={"RAG_INDEX_DIR": str(tmp_path), "USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
