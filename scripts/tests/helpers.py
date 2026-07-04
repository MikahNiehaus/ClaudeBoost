"""
Shared helpers for ClaudeBoost hook tests.

Import from here — not from conftest — since pytest's conftest.py
is not a reliable importable module across different rootdir configurations.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# scripts/ is one level up from scripts/tests/
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
COVERAGERC = Path(__file__).resolve().parent.parent.parent / ".coveragerc"


def run_hook(
    script_name: str,
    fixture: dict,
    env_overrides: dict | None = None,
    base_dir: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a hook script with a JSON fixture on stdin, return the result.

    base_dir overrides SCRIPTS_DIR for hooks that live elsewhere (e.g.
    clean-rag/hooks/) — defaults to SCRIPTS_DIR for every other hook.
    """
    script = (base_dir or SCRIPTS_DIR) / script_name
    env = {**os.environ, **(env_overrides or {})}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(fixture).encode(),
        capture_output=True,
        env=env,
    )


def run_script(
    script_name: str,
    args: list | None = None,
    env_overrides: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run a CLI script with optional args (no stdin fixture), return the result."""
    script = SCRIPTS_DIR / script_name
    env = {**os.environ, **(env_overrides or {})}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)
    return subprocess.run(
        [sys.executable, str(script)] + (args or []),
        capture_output=True,
        env=env,
        input=b"",
    )


def pretooluse(tool_name: str, tool_input: dict) -> dict:
    """Minimal PreToolUse stdin fixture."""
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.json",
        "cwd": "/test/cwd",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "effort": {"level": "medium"},
    }


def posttooluse(tool_name: str, tool_input: dict, tool_response: str = "") -> dict:
    """Minimal PostToolUse stdin fixture."""
    return {
        "session_id": "test-session",
        "transcript_path": "/tmp/test-transcript.json",
        "cwd": "/test/cwd",
        "permission_mode": "default",
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
        "effort": {"level": "medium"},
    }
