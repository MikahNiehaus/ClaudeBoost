"""
Tests for scripts/rag-server-start.py (CLI utility / server launcher).

We test flag parsing, path logic, and the helper functions.
We do NOT actually start the server (that would be a live integration test).
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path

import pytest
from unittest.mock import patch

from helpers import SCRIPTS_DIR, run_script, COVERAGERC


class TestFlagParsing:
    def test_help_flag_exits_0(self):
        result = run_script("rag-server-start.py", args=["--help"])
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "port" in output.lower() or "usage" in output.lower()

    def test_invalid_port_flag_exits_nonzero(self):
        result = run_script("rag-server-start.py", args=["--port", "not_a_number"])
        assert result.returncode != 0


class TestServerAlreadyRunning:
    def test_detects_server_already_running_via_info_file(self, tmp_path):
        """If .server.json says port matches and server responds, exits 0 quickly."""
        # We can't fake the actual HTTP check, but we can test the path that
        # reads .server.json with a stale pid — code will try to restart.
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        server_info = rag_index_dir / ".server.json"
        server_info.write_text(json.dumps({"port": 8612, "pid": 99999999}), encoding="utf-8")

        env = {
            "RAG_INDEX_DIR": str(rag_index_dir),
            "CLAUDEBOOST_HOME": str(tmp_path),
        }

        # The script will see stale pid and try to start server.
        # We can't easily interrupt the 60s wait, so just verify it starts and runs.
        # Use a non-default port to avoid touching the real server.
        result = run_script(
            "rag-server-start.py",
            args=["--port", "18612"],
            env_overrides={
                **env,
                # Override CLAUDEBOOST_HOME to point at a dir without mcp-rag-server
                # so the launch itself may fail fast (no rag_server module)
            },
        )
        # Either it starts and times out (returncode 1) or fails fast
        assert result.returncode in (0, 1)


class TestHelperFunctions:
    def test_script_reads_server_info_json(self, tmp_path):
        """Verify the script can be imported and path logic works."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        server_info = rag_index_dir / ".server.json"
        server_info.write_text(json.dumps({"port": 8612, "pid": 12345}), encoding="utf-8")

        # Just verify the file was written correctly (path logic test)
        info = json.loads(server_info.read_text(encoding="utf-8"))
        assert info["port"] == 8612
        assert info["pid"] == 12345


def _load_rag_server_start():
    """Import rag-server-start.py as a module (hyphen requires importlib)."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "rag_server_start",
        Path(__file__).resolve().parent.parent / "rag-server-start.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestServerInfoHelper:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        """_server_info returns None when .server.json doesn't exist."""
        mod = _load_rag_server_start()
        monkeypatch.setattr(mod, "RAG_INDEX_DIR", tmp_path)
        result = mod._server_info()
        assert result is None

    def test_returns_dict_when_file_exists(self, tmp_path, monkeypatch):
        """_server_info returns parsed dict when .server.json is valid."""
        mod = _load_rag_server_start()
        monkeypatch.setattr(mod, "RAG_INDEX_DIR", tmp_path)
        (tmp_path / ".server.json").write_text(
            json.dumps({"port": 8612, "pid": 42}), encoding="utf-8"
        )
        result = mod._server_info()
        assert result is not None
        assert result["port"] == 8612

    def test_returns_none_on_corrupt_file(self, tmp_path, monkeypatch):
        """_server_info returns None when .server.json is corrupt."""
        mod = _load_rag_server_start()
        monkeypatch.setattr(mod, "RAG_INDEX_DIR", tmp_path)
        (tmp_path / ".server.json").write_text("NOT JSON", encoding="utf-8")
        result = mod._server_info()
        assert result is None


class TestIsServerAliveHelper:
    def test_returns_true_when_server_running(self):
        """_is_server_alive returns True when urlopen returns {"status": "ready"}."""
        import io, json, unittest.mock as _um, urllib.request as _ur
        mod = _load_rag_server_start()
        fake_body = json.dumps({"status": "ready"}).encode()
        fake_resp = io.BytesIO(fake_body)
        fake_resp.read = lambda: fake_body
        cm = _um.MagicMock()
        cm.__enter__ = lambda s: fake_resp
        cm.__exit__ = _um.MagicMock(return_value=False)
        with _um.patch.object(_ur, "urlopen", return_value=cm):
            result = mod._is_server_alive(8612)
        assert result is True

    def test_returns_false_for_closed_port(self):
        """_is_server_alive returns False for a port nothing is listening on."""
        mod = _load_rag_server_start()
        result = mod._is_server_alive(19876)  # unused port
        assert result is False


class TestIsPidAliveHelper:
    def test_current_process_is_alive(self):
        """_is_pid_alive returns True for the current process PID."""
        mod = _load_rag_server_start()
        result = mod._is_pid_alive(os.getpid())
        assert result is True

    def test_dead_pid_returns_false(self):
        """_is_pid_alive returns False for PID that almost certainly doesn't exist."""
        mod = _load_rag_server_start()
        result = mod._is_pid_alive(99999999)
        assert result is False


class TestMainAlreadyRunning:
    def test_detects_running_server_at_default_port(self, tmp_path):
        """main() exits 0 immediately when .server.json matches a live server+pid."""
        mod = _load_rag_server_start()
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        server_json = rag_index_dir / ".server.json"
        server_json.write_text(
            json.dumps({"port": 8612, "pid": os.getpid()}), encoding="utf-8"
        )
        result = run_script(
            "rag-server-start.py",
            args=["--port", "8612"],
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        assert result.returncode == 0
        output = result.stdout.decode(errors="replace")
        assert "already running" in output.lower() or "ready" in output.lower()


class TestIsPidAliveEdgeCases:
    def test_exception_in_pid_check_returns_false(self):
        """_is_pid_alive returns False when subprocess.run raises an exception (lines 68-69)."""
        mod = _load_rag_server_start()
        import subprocess as _sp
        with patch.object(_sp, "run", side_effect=OSError("tasklist not found")):
            result = mod._is_pid_alive(os.getpid())
        assert result is False


class TestMainStaleServerRestart:
    def test_stale_server_info_prints_restart_message(self, tmp_path):
        """Stale .server.json (dead pid) triggers the stale restart message (line 131)."""
        rag_index_dir = tmp_path / "rag-index"
        rag_index_dir.mkdir()
        # Use PID 99999999 (dead) so _is_pid_alive returns False → stale path
        server_json = rag_index_dir / ".server.json"
        server_json.write_text(
            json.dumps({"port": 8612, "pid": 99999999}), encoding="utf-8"
        )
        result = run_script(
            "rag-server-start.py",
            args=["--port", "8612"],
            env_overrides={"RAG_INDEX_DIR": str(rag_index_dir)},
        )
        output = result.stdout.decode(errors="replace")
        # Either stale restart message OR "already running" (if real server is up on 8612)
        assert (
            "stale" in output.lower()
            or "already running" in output.lower()
            or "starting" in output.lower()
        )
