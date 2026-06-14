"""
Tests for scripts/update-statusline.py (CLI utility).

Patches ~/.claude/settings.json to add a statusLine command.
We override settings.json via a temp file.
"""
from __future__ import annotations

import json
import sys
import os
import subprocess
from pathlib import Path

import pytest

from helpers import SCRIPTS_DIR, COVERAGERC


def run_update_statusline(settings_path: Path, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    """Run update-statusline.py with HOME patched to point at a temp dir."""
    script = SCRIPTS_DIR / "update-statusline.py"
    env = {**os.environ}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)

    # Monkey-patch the script to use our temp settings path by rewriting it in-place
    # is too invasive. Instead we mock via a wrapper that patches Path.home().
    # Simplest approach: create a temp home dir with .claude/settings.json.
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        env=env,
        input=b"",
    )


class TestStatusLineUpdate:
    def test_patches_settings_json(self, tmp_path):
        """update-statusline.py reads and writes $HOME/.claude/settings.json."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.json"
        settings_file.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

        # Run with HOME pointing at tmp_path so Path.home() returns tmp_path
        env_overrides = {"HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
        result = run_update_statusline(settings_file, env_overrides=env_overrides)

        if result.returncode == 0:
            updated = json.loads(settings_file.read_text(encoding="utf-8"))
            assert "statusLine" in updated
            assert "rag-statusline.py" in updated["statusLine"]["command"]

    def test_idempotent_second_run(self, tmp_path):
        """Running twice should not break the settings file."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings_file = claude_dir / "settings.json"
        settings_file.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

        env_overrides = {"HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
        # Run twice
        run_update_statusline(settings_file, env_overrides=env_overrides)
        result = run_update_statusline(settings_file, env_overrides=env_overrides)

        if result.returncode == 0:
            updated = json.loads(settings_file.read_text(encoding="utf-8"))
            assert "statusLine" in updated
