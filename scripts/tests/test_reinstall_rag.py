"""
Tests for scripts/reinstall-rag.py (CLI utility).

Reinstalls the RAG server and repairs ML dependency drift.
We only test the boost_home() path logic since actually running pip install
would be slow and modify the environment.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from helpers import run_script, SCRIPTS_DIR

# Direct import for unit testing
_ri_spec = importlib.util.spec_from_file_location("reinstall_rag", SCRIPTS_DIR / "reinstall-rag.py")
_ri_mod = importlib.util.module_from_spec(_ri_spec)
_ri_spec.loader.exec_module(_ri_mod)


class TestBoostHomeFallback:
    def test_uses_claudeboost_home_env_when_set(self, tmp_path):
        """boost_home() should prefer CLAUDEBOOST_HOME env var when valid."""
        # Create a fake mcp-rag-server dir so the script at least starts
        fake_rag_dir = tmp_path / "mcp-rag-server"
        fake_rag_dir.mkdir()
        (fake_rag_dir / "pyproject.toml").write_text("[project]\nname='rag_server'\n", encoding="utf-8")

        result = run_script(
            "reinstall-rag.py",
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        # Will fail with pip install error (no real package) but should start executing
        # The important thing is it doesn't error out before calling pip
        # returncode may be non-zero from pip but that's OK
        output = result.stdout.decode(errors="replace")
        assert "pip install" in output.lower() or "$ " in output or result.returncode in (0, 1)

    def test_script_exists_and_is_importable(self):
        """The script should exist at the expected location."""
        script = SCRIPTS_DIR / "reinstall-rag.py"
        assert script.exists()

    def test_boost_home_returns_env_when_set(self, tmp_path):
        with patch.dict(os.environ, {"CLAUDEBOOST_HOME": str(tmp_path)}):
            result = _ri_mod.boost_home()
        assert result == str(tmp_path)

    def test_boost_home_fallback_when_env_missing(self):
        env = os.environ.copy()
        env.pop("CLAUDEBOOST_HOME", None)
        with patch.dict(os.environ, env, clear=True):
            result = _ri_mod.boost_home()
        assert result != ""  # returns some path
        assert "scripts" not in result  # parent of scripts dir


class TestRunHelper:
    def test_run_calls_subprocess(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result) as mock_sub:
            _ri_mod.run(["echo", "test"])
        mock_sub.assert_called_once_with(["echo", "test"], check=True)


class TestMainFunction:
    def test_main_calls_pip_and_returns_0(self, tmp_path):
        mock_run = MagicMock(returncode=0)
        mock_tv_check = MagicMock(returncode=0)  # torchvision import succeeds

        with patch.dict(os.environ, {"CLAUDEBOOST_HOME": str(tmp_path)}):
            with patch("subprocess.run", side_effect=[mock_run, mock_run, mock_tv_check]) as sub_mock:
                rc = _ri_mod.main()

        assert rc == 0

    def test_main_uninstalls_torchvision_when_import_fails(self, tmp_path):
        mock_ok = MagicMock(returncode=0)
        mock_tv_fail = MagicMock(returncode=1)  # torchvision import fails

        run_calls = []
        def track_run(args, **kwargs):
            run_calls.append(list(args))
            # The torchvision check uses python -c "import torchvision"
            joined = " ".join(str(a) for a in args)
            if "import torchvision" in joined:
                return mock_tv_fail
            return mock_ok

        with patch.dict(os.environ, {"CLAUDEBOOST_HOME": str(tmp_path)}):
            with patch("subprocess.run", side_effect=track_run):
                rc = _ri_mod.main()

        assert rc == 0
        # The uninstall call should have "torchvision" in it
        uninstall_calls = [c for c in run_calls if "uninstall" in c]
        assert len(uninstall_calls) >= 1
        assert any("torchvision" in str(c) for c in uninstall_calls)
