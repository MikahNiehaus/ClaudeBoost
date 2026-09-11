"""Tests for scripts/setup.py — resolving and running the Claude Code CLI.

setup.py shells out to `claude mcp ...` to clear the stale rag-server MCP
registration. On Windows npm installs the CLI as claude.cmd, and a bare
"claude" in an argv list is not launchable at all — subprocess passes no shell
and CreateProcess appends only ".exe", never PATHEXT. The cleanup path used the
bare name and so reported the CLI missing, and skipped, on every standard
Windows install.

Nothing is mocked: a real claude.cmd on an isolated PATH stands in for the npm
shim, and the assertions are about what setup.py printed after really running
it.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from helpers import SCRIPTS_DIR, isolate_path_to

_spec = importlib.util.spec_from_file_location("setup_cli_test", SCRIPTS_DIR / "setup.py")
_setup = importlib.util.module_from_spec(_spec)
sys.modules["setup_cli_test"] = _setup
_spec.loader.exec_module(_setup)

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="the CLI ships as claude.cmd only on Windows"
)


def _shim(tmp_path, mcp_list_output: str):
    """A claude.cmd that answers `mcp list` and accepts `mcp remove`."""
    shim_dir = tmp_path / "fake_bin"
    shim_dir.mkdir()
    body = f'if "%2"=="list" echo {mcp_list_output}\r\n' if mcp_list_output else ""
    (shim_dir / "claude.cmd").write_text(
        f"@echo off\r\n{body}exit /b 0\r\n", encoding="ascii"
    )
    return shim_dir


def test_claude_cmd_resolves_a_shim_that_subprocess_can_launch(tmp_path, monkeypatch):
    """The resolved command must actually start, not merely be found."""
    isolate_path_to(monkeypatch, _shim(tmp_path, ""))

    resolved = _setup.claude_cmd()
    assert resolved is not None
    assert resolved[0].lower().endswith("claude.cmd"), resolved

    probe = subprocess.run(resolved + ["--version"], capture_output=True, text=True, timeout=30)
    assert probe.returncode == 0, probe.stderr


def test_cleanup_removes_the_stale_rag_server_entry(tmp_path, monkeypatch, capsys):
    """With the CLI on PATH, the cleanup runs instead of skipping."""
    isolate_path_to(monkeypatch, _shim(tmp_path, "rag-server: npx -y rag-server stdio - Connected"))

    _setup._cleanup_mcp_registration()

    out = capsys.readouterr().out
    assert "removed stale rag-server entry" in out, out
    assert "not found" not in out, out


def test_cleanup_reports_nothing_to_remove_when_not_registered(tmp_path, monkeypatch, capsys):
    """An empty `mcp list` means there is nothing to clean, not a failure."""
    isolate_path_to(monkeypatch, _shim(tmp_path, ""))

    _setup._cleanup_mcp_registration()

    out = capsys.readouterr().out
    assert "nothing to remove" in out, out


def test_cleanup_skips_when_no_cli_is_on_path(tmp_path, monkeypatch, capsys):
    """No CLI is a skip, never a crash — setup must finish its other steps."""
    empty = tmp_path / "empty_bin"
    empty.mkdir()
    isolate_path_to(monkeypatch, empty)

    _setup._cleanup_mcp_registration()

    assert "claude CLI not found" in capsys.readouterr().out
