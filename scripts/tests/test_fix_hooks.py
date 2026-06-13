"""
Tests for scripts/fix_hooks.py — hook repair utility.

Removes stale hook entries ($CLAUDEBOOST_HOME references or nonexistent paths).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import importlib.util

_spec = importlib.util.spec_from_file_location("fix_hooks", SCRIPTS_DIR / "fix_hooks.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

hook_stale = _mod.hook_stale

from helpers import run_script


class TestHookStale:
    def test_stale_when_claudeboost_home_present(self):
        assert hook_stale('python "$CLAUDEBOOST_HOME/scripts/foo.py"') is True

    def test_stale_when_py_file_missing(self, tmp_path):
        missing_path = tmp_path / "nonexistent.py"
        assert hook_stale(f'python "{missing_path}"') is True

    def test_not_stale_when_py_file_exists(self, tmp_path):
        real_file = tmp_path / "existing.py"
        real_file.write_text("pass", encoding="utf-8")
        assert hook_stale(f'python "{real_file}"') is False

    def test_not_stale_for_env_var_path(self):
        # Path with % env var reference — can't verify, treat as not stale
        assert hook_stale(r'python "%SOME_VAR%\scripts\foo.py"') is False

    def test_not_stale_for_dollar_var_path(self):
        # $VAR in path (not $CLAUDEBOOST_HOME) — can't verify, not stale
        assert hook_stale('python "$OTHER_VAR/scripts/foo.py"') is False

    def test_not_stale_for_command_without_py(self):
        assert hook_stale("echo hello") is False


class TestFixHooksCLI:
    def test_exits_0_on_no_settings(self, tmp_path):
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_exits_0_when_no_stale_hooks(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        real_script = SCRIPTS_DIR / "boost-inline.py"
        settings = {
            "hooks": {
                "PreToolUse": [{
                    "hooks": [{"command": f'python "{real_script}"'}]
                }]
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        output = result.stdout.decode("utf-8", errors="replace")
        assert "No stale" in output or "nothing to fix" in output.lower()

    def test_removes_stale_hooks_with_claudeboost_home(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "hooks": {
                "PreToolUse": [{
                    "hooks": [{
                        "command": 'python "$CLAUDEBOOST_HOME/scripts/old-script.py"'
                    }]
                }]
            }
        }
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        # Stale entry should be removed
        updated = json.loads(settings_path.read_text(encoding="utf-8"))
        hooks = updated.get("hooks", {})
        # Either the hook type is gone or the entry is empty
        pre_entries = hooks.get("PreToolUse", [])
        for entry in pre_entries:
            for h in entry.get("hooks", []):
                assert "$CLAUDEBOOST_HOME" not in h.get("command", "")

    def test_removes_hooks_referencing_missing_py_files(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        missing_script = tmp_path / "no_exist.py"
        settings = {
            "hooks": {
                "PostToolUse": [{
                    "hooks": [{"command": f'python "{missing_script}"'}]
                }]
            }
        }
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        updated = json.loads(settings_path.read_text(encoding="utf-8"))
        # PostToolUse entries should be gone
        assert "PostToolUse" not in updated.get("hooks", {})

    def test_exits_1_on_malformed_json(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("INVALID{JSON", encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 1

    def test_clears_ensure_setup_sentinel(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        sentinel = claude_dir / ".ensure-setup-triggered"
        sentinel.write_text("triggered", encoding="utf-8")
        (claude_dir / "settings.json").write_text(json.dumps({"hooks": {
            "PreToolUse": [{"hooks": [{"command": 'python "$CLAUDEBOOST_HOME/old.py"'}]}]
        }}), encoding="utf-8")
        run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert not sentinel.exists()

    def test_empty_hooks_block_exits_0(self, tmp_path):
        """settings.json with empty hooks dict triggers lines 71-72."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text(json.dumps({"hooks": {}}), encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        output = result.stdout.decode("utf-8", errors="replace")
        assert "nothing to fix" in output.lower() or "no hooks" in output.lower()

    def test_entry_without_inner_hooks_kept(self, tmp_path):
        """Hook entry with no inner 'hooks' key is kept as-is (lines 81-82)."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {
            "hooks": {
                "PreToolUse": [{"matcher": ".*", "command": "echo hi"}]
            }
        }
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        updated = json.loads(settings_path.read_text(encoding="utf-8"))
        assert updated["hooks"]["PreToolUse"][0]["command"] == "echo hi"

    def test_sentinel_unlink_failure_silently_ignored(self, tmp_path):
        """OSError on sentinel unlink is ignored (lines 106-107)."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        sentinel = claude_dir / ".ensure-setup-triggered"
        sentinel.mkdir()  # directory: unlink raises
        (claude_dir / "settings.json").write_text(json.dumps({"hooks": {
            "PreToolUse": [{"hooks": [{"command": 'python "$CLAUDEBOOST_HOME/old.py"'}]}]
        }}), encoding="utf-8")
        result = run_script(
            "fix_hooks.py",
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_write_failure_returns_1(self, tmp_path):
        """OSError on settings.json write returns 1 (lines 115-118)."""
        import importlib.util as _ilu
        from unittest.mock import patch
        spec = _ilu.spec_from_file_location("fix_hooks", SCRIPTS_DIR / "fix_hooks.py")
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)

        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        stale_cmd = 'python "$CLAUDEBOOST_HOME/scripts/old-script.py"'
        settings = {"hooks": {"PreToolUse": [{"hooks": [{"command": stale_cmd}]}]}}
        settings_path = claude_dir / "settings.json"
        settings_path.write_text(json.dumps(settings), encoding="utf-8")

        orig_write_text = Path.write_text

        def fail_write(self, *args, **kwargs):
            if "settings.json" in str(self):
                raise OSError("file locked")
            return orig_write_text(self, *args, **kwargs)

        mod.SETTINGS_PATH = settings_path
        mod.SENTINEL_PATH = claude_dir / ".ensure-setup-triggered"

        with patch.object(Path, "write_text", fail_write):
            result = mod.main()

        assert result == 1
