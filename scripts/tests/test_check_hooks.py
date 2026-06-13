"""
Tests for scripts/check-hooks.py — hook installation verification.

Checks if a named hook exists in ~/.claude/settings.json.
Exit 0 = present, nonzero = missing or settings not found.
"""
from __future__ import annotations

import json
from helpers import run_script


class TestCheckHooks:
    def test_default_hook_name_pretooluse(self, tmp_path):
        # Create a minimal settings.json with PreToolUse
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {"hooks": {"PreToolUse": [{"hooks": [{"command": "echo test"}]}]}}
        (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "check-hooks.py",
            args=["PreToolUse"],
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_missing_hook_exits_nonzero(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {"hooks": {}}
        (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "check-hooks.py",
            args=["SessionStart"],
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode != 0

    def test_missing_settings_file_exits_nonzero(self, tmp_path):
        result = run_script(
            "check-hooks.py",
            args=["PreToolUse"],
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode != 0

    def test_hook_present_prints_ok(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {"hooks": {"Stop": [{"hooks": [{"command": "echo stop"}]}]}}
        (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        result = run_script(
            "check-hooks.py",
            args=["Stop"],
            env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
        )
        assert result.returncode == 0
        output = result.stdout.decode("utf-8", errors="replace")
        assert "OK" in output or "hooks" in output.lower()

    def test_all_six_hooks_present(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        hooks = {h: [{"hooks": [{"command": "echo"}]}]
                 for h in ("SessionStart", "PreToolUse", "PostToolUse", "PreCompact", "UserPromptSubmit", "Stop")}
        settings = {"hooks": hooks}
        (claude_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
        for hook_name in ("SessionStart", "PreToolUse", "PostToolUse", "PreCompact", "UserPromptSubmit", "Stop"):
            result = run_script(
                "check-hooks.py",
                args=[hook_name],
                env_overrides={"USERPROFILE": str(tmp_path), "HOME": str(tmp_path)},
            )
            assert result.returncode == 0, f"Expected {hook_name} to be found"
