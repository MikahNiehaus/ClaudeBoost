"""
Tests for scripts/tdd-guard.py (PreToolUse TDD enforcement hook).

The hook reads {"tool_name": "Edit", "tool_input": {"file_path": "..."}} on stdin.
Exit codes:
  0 = allow (exempt, test file, soft mode, off, or test found)
  2 = block (strict mode, no test found for source file)
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from helpers import run_hook, pretooluse


def _edit(file_path: str) -> dict:
    return pretooluse("Edit", {"file_path": file_path})


def _write(file_path: str, content: str = "") -> dict:
    return pretooluse("Write", {"file_path": file_path, "content": content})


# ---------------------------------------------------------------------------
# EXEMPT: paths that should always pass regardless of TDD state
# ---------------------------------------------------------------------------

class TestExemptions:
    """Files in exempt directories pass without test checks."""

    def test_workspace_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/workspace/task/file.py"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_state_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/state/config.json"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_docs_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/docs/README.md"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_knowledge_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/knowledge/topic.xml"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_plans_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/plans/plan.md"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_claude_dir_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/.claude/settings.json"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_claudeboost_dir_exempt(self):
        r = run_hook("tdd-guard.py", _edit("/project/.claudeboost/config.json"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# TEST FILE DETECTION: editing test files should always be allowed
# ---------------------------------------------------------------------------

class TestTestFileDetection:
    """Writing test files is always allowed (you ARE writing the test)."""

    def test_python_test_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/tests/test_auth.py"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_go_test_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/auth_test.go"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_js_test_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/auth.test.ts"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_spec_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/auth.spec.js"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_csharp_test_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/AuthTests.cs"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_ruby_spec_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/spec/auth_spec.rb"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_tests_dir_file_allowed(self):
        r = run_hook("tdd-guard.py", _edit("/project/__tests__/auth.js"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# MODE: off disables entirely
# ---------------------------------------------------------------------------

class TestOffMode:
    """Off mode allows everything without checking."""

    def test_off_allows_source_without_test(self):
        r = run_hook("tdd-guard.py", _edit("/project/src/auth.py"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "off"})
        assert r.returncode == 0
        assert b"TDD Guard" not in r.stderr


# ---------------------------------------------------------------------------
# SOFT MODE: warns but allows (default)
# ---------------------------------------------------------------------------

class TestSoftMode:
    """Soft mode (default) issues a warning but exits 0."""

    def test_soft_warns_on_source_without_test(self):
        """Source file with no test changes: exit 0 but stderr warning."""
        r = run_hook("tdd-guard.py", _edit("/project/src/auth.py"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "soft"})
        assert r.returncode == 0
        assert b"TDD Guard" in r.stderr
        assert b"Write the failing test FIRST" in r.stderr

    def test_default_mode_is_soft(self):
        """No env var set means soft mode."""
        env = dict(os.environ)
        env.pop("CLAUDEBOOST_TDD_GUARD", None)
        r = run_hook("tdd-guard.py", _edit("/project/src/auth.py"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": ""})
        # Empty string should fall back to "soft" default
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# STRICT MODE: blocks source edits without test changes
# ---------------------------------------------------------------------------

class TestStrictMode:
    """Strict mode hard blocks (exit 2) when no test found."""

    def test_strict_blocks_source_without_test(self):
        """Source file edit without test changes: exit 2."""
        r = run_hook("tdd-guard.py", _edit("/project/src/auth.py"),
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 2
        assert b"TDD Guard" in r.stderr
        assert b"Write the failing test FIRST" in r.stderr


# ---------------------------------------------------------------------------
# UNGATED TOOLS: Read, Grep, Bash etc. always pass
# ---------------------------------------------------------------------------

class TestNonGatedTools:
    """Tools other than Edit/Write/MultiEdit are not gated."""

    def test_read_passes(self):
        fixture = pretooluse("Read", {"file_path": "/project/src/auth.py"})
        r = run_hook("tdd-guard.py", fixture,
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_bash_passes(self):
        fixture = pretooluse("Bash", {"command": "echo hello"})
        r = run_hook("tdd-guard.py", fixture,
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0

    def test_grep_passes(self):
        fixture = pretooluse("Grep", {"pattern": "auth", "path": "/project"})
        r = run_hook("tdd-guard.py", fixture,
                     env_overrides={"CLAUDEBOOST_TDD_GUARD": "strict"})
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# AUTO MODE: bypasses TDD guard
# ---------------------------------------------------------------------------

class TestAutoMode:
    """ClaudeBoost AUTO mode bypasses TDD enforcement."""

    def test_auto_mode_bypasses(self, tmp_path):
        """When claudeboost-mode.json says AUTO, all edits pass."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "claudeboost-mode.json").write_text(
            json.dumps({"mode": "AUTO"}), encoding="utf-8"
        )
        r = run_hook(
            "tdd-guard.py",
            _edit("/project/src/auth.py"),
            env_overrides={
                "CLAUDEBOOST_TDD_GUARD": "strict",
                "CLAUDEBOOST_HOME": str(tmp_path),
            },
        )
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# UNIT TESTS: internal functions
# ---------------------------------------------------------------------------

class TestInternalFunctions:
    """Direct tests on internal helpers."""

    def test_is_test_file_python(self):
        from importlib import import_module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tdd_guard",
            str(Path(__file__).resolve().parent.parent / "tdd-guard.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert mod._is_test_file("test_auth.py") is True
        assert mod._is_test_file("auth_test.go") is True
        assert mod._is_test_file("auth.test.ts") is True
        assert mod._is_test_file("auth.spec.js") is True
        assert mod._is_test_file("AuthTests.cs") is True
        assert mod._is_test_file("auth_spec.rb") is True
        assert mod._is_test_file("auth.py") is False
        assert mod._is_test_file("main.go") is False
        assert mod._is_test_file("index.ts") is False

    def test_has_corresponding_test(self):
        from importlib import import_module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "tdd_guard",
            str(Path(__file__).resolve().parent.parent / "tdd-guard.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Python convention: test_auth.py is a test for auth.py
        assert mod._has_corresponding_test("src/auth.py", ["tests/test_auth.py"]) is True
        # Go convention: auth_test.go is a test for auth.go
        assert mod._has_corresponding_test("auth.go", ["auth_test.go"]) is True
        # JS convention: auth.test.ts is a test for auth.ts
        assert mod._has_corresponding_test("src/auth.ts", ["src/auth.test.ts"]) is True
        # No match
        assert mod._has_corresponding_test("src/auth.py", ["src/other.py"]) is False
        # Any test file in changed files counts
        assert mod._has_corresponding_test("src/auth.py", ["test_something.py"]) is True
