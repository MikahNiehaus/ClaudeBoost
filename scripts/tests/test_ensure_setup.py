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
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import SCRIPTS_DIR, COVERAGERC


#: Written by the stub setup.py so a test can prove which script actually ran.
STUB_MARKER_NAME = "stub-setup-ran.txt"


def _install_stub_setup(tmp_home: Path) -> Path:
    """Point ensure-setup.py at a harmless setup.py and return the marker path.

    This is not tidiness, it is containment, and it belongs in the harness so no
    future test in this file can opt out of it by accident.

    ensure-setup.py's _find_setup_script() tries ~/.claude/claudeboost-home.txt
    FIRST and only then falls back to a __file__ relative path. Run from inside
    the repo with no claudeboost-home.txt, that fallback resolves to the real
    scripts/setup.py, and main() then launches it with DETACHED_PROCESS. What
    that actually did, measured on 2026-08-26:

        setup.py -> clean-rag/install.py -> pip install -r requirements.txt

    into the live venv, still running after pytest exited, because DETACHED
    means it does not die with its parent. The same thing on 2026-08-24 left a
    HuggingFace cache inside a pytest temp directory, which the real server then
    logged:

        Could not reconcile the snapshot for nomic-ai/CodeRankEmbed (OSError:
        [WinError 1314] ... -> 'C:\\Users\\...\\pytest-1136\\
        test_exits_0_when_no_home_and_0\\.cache\\huggingface\\hub\\...')

    `test_exits_0_when_no_home_and_0` is this file's own temp directory name.
    A test suite that reinstalls the machine it is running on is not a test
    suite, so the first candidate is always a stub from here on.
    """
    claude_dir = tmp_home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    stub_repo = tmp_home / "stub-claudeboost"
    (stub_repo / "scripts").mkdir(parents=True, exist_ok=True)
    marker = tmp_home / STUB_MARKER_NAME
    # Writes the marker and exits. Enough to prove the spawn happened and that
    # it landed here rather than on the real installer.
    (stub_repo / "scripts" / "setup.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (claude_dir / "claudeboost-home.txt").write_text(str(stub_repo), encoding="utf-8")
    return marker


def _run_ensure_setup(tmp_home: Path, env_overrides: dict | None = None) -> subprocess.CompletedProcess:
    script = SCRIPTS_DIR / "ensure-setup.py"
    env = {**os.environ}
    if COVERAGERC.exists():
        env["COVERAGE_PROCESS_START"] = str(COVERAGERC)

    # Provide a temp HOME so sentinel and settings.json go there
    env["HOME"] = str(tmp_home)
    env["USERPROFILE"] = str(tmp_home)

    # Unconditional. See _install_stub_setup for what happens without it.
    _install_stub_setup(tmp_home)

    if env_overrides:
        env.update(env_overrides)

    fixture = {"hook_event_name": "UserPromptSubmit", "session_id": "test", "prompt": "hello"}
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(fixture).encode(),
        capture_output=True,
        env=env,
    )


def _wait_for_marker(marker: Path, timeout_s: float = 15.0) -> bool:
    """Wait for the stub's marker file. The spawn is detached, so it is a race.

    Returns False on timeout rather than raising, so the caller decides whether
    a missing marker is a failure or the expected outcome.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if marker.exists():
            return True
        time.sleep(0.1)
    return marker.exists()


class TestSetupAlreadyDone:
    def test_silent_when_claudeboost_home_set_via_env(self, tmp_path):
        # Create a minimal stub so the stale-path check in _needs_setup() passes
        fake_boost = tmp_path / "claudeboost"
        (fake_boost / "scripts").mkdir(parents=True)
        (fake_boost / "scripts" / "setup.py").write_text("# stub", encoding="utf-8")
        result = _run_ensure_setup(
            tmp_path,
            env_overrides={"CLAUDEBOOST_HOME": str(fake_boost)},
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
    def test_announces_auto_setup_and_spawns_the_resolved_script(self, tmp_path):
        """No CLAUDEBOOST_HOME and none in settings, so setup is needed.

        Was `test_exits_0_when_no_home_and_no_setup_script`. The old name was
        wrong: there was always a setup script to find, because
        _find_setup_script() falls back to a __file__ relative path and this
        runs from inside the repo. So it resolved the REAL scripts/setup.py and
        launched it detached, which is how a test run reinstalled the machine.
        See _install_stub_setup.

        The old body could not catch that either. Its only assertion was
        guarded by `if result.stdout.strip():`, so an empty stdout asserted
        nothing at all and the test passed whatever happened.
        """
        result = _run_ensure_setup(
            tmp_path,
            env_overrides={"CLAUDEBOOST_HOME": ""},
        )
        assert result.returncode == 0
        assert result.stdout.strip(), "setup was needed but nothing was announced"

        output = json.loads(result.stdout)
        ctx = output.get("additionalContext", "")
        assert "AUTO-SETUP" in ctx.upper(), ctx

        marker = tmp_path / STUB_MARKER_NAME
        assert _wait_for_marker(marker), (
            "the spawned setup script never wrote its marker, so either nothing "
            "was spawned or something other than the stub was"
        )
        assert marker.read_text(encoding="utf-8") == "ran"

    def test_the_real_repo_setup_is_never_the_spawn_target(self, tmp_path):
        """The containment itself, stated as an assertion rather than a comment.

        Reads the path ensure-setup.py would resolve, and fails if it is the
        repo's own installer. This is the regression guard: it fails on the
        exact arrangement that let a test run pip install into the live venv.
        """
        mod = _load_ensure_setup()
        _install_stub_setup(tmp_path)

        with patch.object(Path, "home", lambda: tmp_path):
            resolved = mod._find_setup_script()

        assert resolved is not None
        real_setup = (SCRIPTS_DIR / "setup.py").resolve()
        assert resolved.resolve() != real_setup, (
            f"ensure-setup.py resolved the real installer at {real_setup}. "
            f"Running it detached is what reinstalled the machine mid test run."
        )
        assert resolved.resolve().is_relative_to(tmp_path.resolve()), resolved

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
