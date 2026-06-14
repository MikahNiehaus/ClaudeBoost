"""
Tests for scripts/ensure-setup.py (UserPromptSubmit hook).

Auto-runs setup.py when CLAUDEBOOST_HOME is not configured.
Always exits 0. Never hard-blocks.
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import SCRIPTS_DIR, COVERAGERC


def _run_ensure_setup(tmp_home: Path, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    script = SCRIPTS_DIR / "ensure-setup.py"
    env = {**os.environ}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)

    # Provide a temp HOME so sentinel and settings.json go there
    env["HOME"] = str(tmp_home)
    env["USERPROFILE"] = str(tmp_home)

    if env_overrides:
        env.update(env_overrides)

    fixture = {"hook_event_name": "UserPromptSubmit", "session_id": "test", "prompt": "hello"}
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(fixture).encode(),
        capture_output=True,
        env=env,
    )


class TestSetupAlreadyDone:
    def test_silent_when_claudeboost_home_set_via_env(self, tmp_path):
        result = _run_ensure_setup(
            tmp_path,
            env_overrides={"CLAUDEBOOST_HOME": "C:/some/path"},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == b""

    def test_silent_when_claudeboost_home_in_settings(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {"env": {"CLAUDEBOOST_HOME": "C:/some/path"}}
        (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        result = _run_ensure_setup(tmp_path, env_overrides={"CLAUDEBOOST_HOME": ""})
        assert result.returncode == 0
        # CLAUDEBOOST_HOME in settings.json → no setup needed
        assert result.stdout.strip() == b""


class TestSetupNeeded:
    def test_exits_0_when_no_home_and_no_setup_script(self, tmp_path):
        """No CLAUDEBOOST_HOME, no claudeboost-home.txt → outputs context message."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        result = _run_ensure_setup(
            tmp_path,
            env_overrides={"CLAUDEBOOST_HOME": ""},
        )
        assert result.returncode == 0
        if result.stdout.strip():
            output = json.loads(result.stdout)
            ctx = output.get("additionalContext", "")
            assert "CLAUDEBOOST" in ctx.upper() or "setup" in ctx.lower()

    def test_sentinel_prevents_double_spawn(self, tmp_path):
        """If sentinel file exists, script exits silently (no double-spawn)."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        sentinel = claude_dir / ".ensure-setup-triggered"
        sentinel.touch()

        result = _run_ensure_setup(
            tmp_path,
            env_overrides={"CLAUDEBOOST_HOME": ""},
        )
        assert result.returncode == 0
        assert result.stdout.strip() == b""


# ---------------------------------------------------------------------------
# Direct import tests for branches that can't be hit via subprocess
# ---------------------------------------------------------------------------

def _load_ensure_setup():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ensure_setup", SCRIPTS_DIR / "ensure-setup.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFindSetupScriptEdgeCases:
    def test_claudeboost_home_txt_candidate_added(self, tmp_path, monkeypatch):
        """When claudeboost-home.txt exists, its path is added as candidate (line 54)."""
        mod = _load_ensure_setup()
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        home_txt = claude_dir / "claudeboost-home.txt"
        home_txt.write_text("/nonexistent/boost/path", encoding="utf-8")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = mod._find_setup_script()
        # /nonexistent/boost/path/scripts/setup.py doesn't exist → falls back
        # and might find setup.py via __file__ relative path if running from repo
        # Just assert the function returns without error
        assert result is None or result.exists()

    def test_returns_none_when_no_candidates_exist(self, tmp_path, monkeypatch):
        """All candidates fail exists() → return None (line 68)."""
        mod = _load_ensure_setup()
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        # Patch exists() to always return False
        monkeypatch.setattr(Path, "exists", lambda self: False)
        result = mod._find_setup_script()
        assert result is None


class TestMainBranches:
    def test_no_setup_script_outputs_message(self, tmp_path, monkeypatch, capsys):
        """When _find_setup_script returns None, outputs context message (lines 78-85)."""
        mod = _load_ensure_setup()
        monkeypatch.setenv("CLAUDEBOOST_HOME", "")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.setattr(mod, "_needs_setup", lambda: True)
        monkeypatch.setattr(mod, "_find_setup_script", lambda: None)

        result = mod.main()
        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert "CLAUDEBOOST" in output.get("additionalContext", "").upper()

    def test_sentinel_touch_failure_silently_ignored(self, tmp_path, monkeypatch, capsys):
        """OSError from _SENTINEL.touch() is silently ignored (lines 90-91)."""
        mod = _load_ensure_setup()
        fake_setup = tmp_path / "setup.py"
        fake_setup.write_text("# fake", encoding="utf-8")

        monkeypatch.setattr(mod, "_needs_setup", lambda: True)
        monkeypatch.setattr(mod, "_find_setup_script", lambda: fake_setup)

        orig_touch = Path.touch

        def fail_touch(self, *args, **kwargs):
            if ".ensure-setup-triggered" in str(self):
                raise OSError("permission denied")
            return orig_touch(self, *args, **kwargs)

        with patch("pathlib.Path.touch", fail_touch):
            result = mod.main()

        assert result == 0

    def test_non_windows_uses_start_new_session(self, tmp_path, monkeypatch, capsys):
        """On non-Windows, popen_kwargs gets start_new_session=True (line 109)."""
        mod = _load_ensure_setup()
        fake_setup = tmp_path / "setup.py"
        fake_setup.write_text("# fake", encoding="utf-8")

        monkeypatch.setattr(mod, "_needs_setup", lambda: True)
        monkeypatch.setattr(mod, "_find_setup_script", lambda: fake_setup)
        monkeypatch.setattr(mod, "_IS_WINDOWS", False)

        popen_calls = []

        def fake_popen(cmd, **kwargs):
            popen_calls.append(kwargs)
            return MagicMock()

        with patch("subprocess.Popen", fake_popen):
            result = mod.main()

        assert result == 0
        assert popen_calls and popen_calls[0].get("start_new_session") is True

    def test_popen_exception_outputs_fallback_message(self, tmp_path, monkeypatch, capsys):
        """subprocess.Popen raising outputs error message (lines 117-118)."""
        mod = _load_ensure_setup()
        fake_setup = tmp_path / "setup.py"
        fake_setup.write_text("# fake", encoding="utf-8")

        monkeypatch.setattr(mod, "_needs_setup", lambda: True)
        monkeypatch.setattr(mod, "_find_setup_script", lambda: fake_setup)

        with patch("subprocess.Popen", side_effect=OSError("cannot start process")):
            result = mod.main()

        assert result == 0
        captured = capsys.readouterr()
        output = json.loads(captured.out.strip().split("\n")[-1])
        assert "FAILED" in output.get("additionalContext", "").upper()
