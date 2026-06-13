"""
Tests for scripts/boost-run.py — ClaudeBoost activation orchestrator.

Tests guard logic and mode-switching (true/false args) without starting RAG server.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from helpers import run_script


class TestBoostRunModeSwitch:
    def test_boost_true_exits_0(self, tmp_path):
        result = run_script(
            "boost-run.py",
            args=["true"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_boost_true_writes_injection_file(self, tmp_path):
        (tmp_path / "state").mkdir()
        run_script(
            "boost-run.py",
            args=["true"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        inj_path = tmp_path / "state" / "boost-injection.json"
        assert inj_path.exists()
        data = json.loads(inj_path.read_text(encoding="utf-8"))
        assert data["mode"] == "true"

    def test_boost_false_exits_0(self, tmp_path):
        result = run_script(
            "boost-run.py",
            args=["false"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 0

    def test_boost_false_writes_injection_file(self, tmp_path):
        (tmp_path / "state").mkdir()
        run_script(
            "boost-run.py",
            args=["false"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        inj_path = tmp_path / "state" / "boost-injection.json"
        assert inj_path.exists()
        data = json.loads(inj_path.read_text(encoding="utf-8"))
        assert data["mode"] == "false"

    def test_unknown_arg_exits_2(self, tmp_path):
        result = run_script(
            "boost-run.py",
            args=["invalid-mode"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        assert result.returncode == 2

    def test_unknown_arg_prints_error(self, tmp_path):
        result = run_script(
            "boost-run.py",
            args=["invalid-mode"],
            env_overrides={"CLAUDEBOOST_HOME": str(tmp_path)},
        )
        output = result.stdout.decode("utf-8", errors="replace")
        assert "Unknown" in output or "invalid" in output.lower()


class TestBoostRunHelpers:
    """Test the helper functions by direct import."""

    def _load_mod(self, tmp_path):
        """Load boost-run module. STATE is patched AFTER exec so it overrides the module-level constant."""
        import uuid
        # Use a unique module name each time to avoid cached module reuse across tests
        mod_name = f"boost_run_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(mod_name, SCRIPTS_DIR / "boost-run.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Patch after loading — module-level constants are set during exec_module
        mod.STATE = tmp_path / "state"
        mod.BOOST_HOME = tmp_path
        return mod

    def test_write_injection_creates_file(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod._write_injection("verify")
        inj_path = tmp_path / "state" / "boost-injection.json"
        assert inj_path.exists()
        data = json.loads(inj_path.read_text(encoding="utf-8"))
        assert data["mode"] == "verify"

    def test_temp_dir_returns_path(self, tmp_path):
        mod = self._load_mod(tmp_path)
        result = mod._temp_dir()
        assert isinstance(result, Path)

    def test_step_privacy_exits_without_crash(self, tmp_path):
        mod = self._load_mod(tmp_path)
        # step_privacy just prints and doesn't raise
        mod.step_privacy()  # should not raise

    def test_step_rules_returns_bool(self, tmp_path):
        mod = self._load_mod(tmp_path)
        result = mod.step_rules()
        assert isinstance(result, bool)

    def test_step_mode_returns_string(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mode = mod.step_mode()
        assert isinstance(mode, str)
        assert mode in ("CONSULT", "AUTO")

    def test_step_mode_reads_mode_file(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        (tmp_path / "state" / "claudeboost-mode.json").write_text(
            json.dumps({"mode": "AUTO"}), encoding="utf-8"
        )
        mod = self._load_mod(tmp_path)
        mode = mod.step_mode()
        assert mode == "AUTO"

    def test_step_workspaces_empty_dir(self, tmp_path):
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert active == []

    def test_step_workspaces_finds_active(self, tmp_path):
        ws = tmp_path / "workspace" / "task-abc"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text("## Status\nin progress", encoding="utf-8")
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert "task-abc" in active

    def test_run_returns_tuple(self, tmp_path):
        mod = self._load_mod(tmp_path)
        rc, out = mod._run([sys.executable, "--version"])
        assert isinstance(rc, int)
        assert isinstance(out, str)

    def test_run_handles_timeout(self, tmp_path):
        mod = self._load_mod(tmp_path)
        # Very short timeout should trigger TimeoutExpired
        rc, out = mod._run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=1)
        assert rc == 124  # timed out

    def test_run_handles_file_not_found(self, tmp_path):
        mod = self._load_mod(tmp_path)
        rc, out = mod._run(["nonexistent_binary_xyz"])
        assert rc == 127

    # ------------------------------------------------------------------
    # _get / _post — mock urlopen so no live server required
    # ------------------------------------------------------------------

    def _make_urlopen(self, response_body: bytes):
        """Return a context manager mock that reads response_body."""
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=cm)
        cm.__exit__ = MagicMock(return_value=False)
        cm.read = MagicMock(return_value=response_body)
        return cm

    def test_get_returns_parsed_json(self, tmp_path):
        mod = self._load_mod(tmp_path)
        cm = self._make_urlopen(b'{"status": "ready"}')
        with patch("urllib.request.urlopen", return_value=cm):
            result = mod._get("/status")
        assert result == {"status": "ready"}

    def test_post_returns_parsed_json(self, tmp_path):
        mod = self._load_mod(tmp_path)
        cm = self._make_urlopen(b'{"ok": true}')
        with patch("urllib.request.urlopen", return_value=cm):
            result = mod._post("/context", {"agent": "test"})
        assert result["ok"] is True

    # ------------------------------------------------------------------
    # step_banner
    # ------------------------------------------------------------------

    def test_step_banner_runs_without_crash(self, tmp_path):
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        mod.BOOST_HOME = tmp_path
        # _run returns empty output; rglob finds nothing
        with patch.object(mod, "_run", return_value=(0, "CLAUDE BOOST\n")):
            mod.step_banner()  # should not raise

    # ------------------------------------------------------------------
    # step_rag — all main branches
    # ------------------------------------------------------------------

    def test_step_rag_server_not_ready(self, tmp_path):
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        def fake_run(args, timeout=60):
            return 0, "started\n"

        with patch.object(mod, "_run", side_effect=fake_run):
            # _get always raises — server never comes up within deadline
            with patch.object(mod, "_get", side_effect=Exception("connection refused")):
                import time
                # Speed up by making monotonic advance past deadline immediately
                original = time.monotonic
                call_count = [0]
                def fast_monotonic():
                    call_count[0] += 1
                    # After 2 calls, pretend deadline has passed
                    return original() + (100 if call_count[0] > 2 else 0)
                with patch("time.monotonic", side_effect=fast_monotonic):
                    with patch("time.sleep"):
                        result = mod.step_rag()
        assert result.get("ready") is False

    def test_step_rag_server_ready(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        status_resp = {
            "status": "ready",
            "model": "test-model",
            "embedding_dimensions": 384,
            "collections": {
                "knowledge": {"chunks": 100, "files": 10},
                "agents": {"chunks": 50, "files": 5},
            },
            "dimension_mismatch": [],
        }

        def fake_run(args, timeout=60):
            return 0, "server already running\n"

        get_calls = [0]
        def fake_get(path, timeout=5):
            get_calls[0] += 1
            return status_resp

        def fake_post(path, body, timeout=300):
            if path == "/warmup":
                return {"ready": True}
            if path == "/context":
                return {"total_tokens_approx": 1000, "sources_used": 5}
            if path == "/index":
                return {"files_indexed": 50, "chunks_created": 200, "files_failed": 0, "graph": {"resolved": 10, "edges": 8}}
            return {}

        with patch.object(mod, "_run", side_effect=fake_run):
            with patch.object(mod, "_get", side_effect=fake_get):
                with patch.object(mod, "_post", side_effect=fake_post):
                    result = mod.step_rag()

        assert result.get("ready") is True
        assert result.get("healed") == []

    def test_step_rag_heals_dimension_mismatch(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        status_resp = {
            "status": "ready",
            "model": "new-model",
            "embedding_dimensions": 768,
            "collections": {
                "knowledge": {"chunks": 0, "files": 0},
                "agents": {"chunks": 0, "files": 0},
            },
            "dimension_mismatch": ["knowledge"],
        }

        def fake_run(args, timeout=60):
            return 0, "server started\n"

        def fake_get(path, timeout=5):
            return status_resp

        def fake_post(path, body, timeout=300):
            if path == "/warmup":
                return {"ready": True}
            if path == "/context":
                return {"total_tokens_approx": 500, "sources_used": 2}
            if path == "/index":
                if body.get("force"):
                    return {"files_indexed": 10, "chunks_created": 50, "files_failed": 0, "graph": {}}
                return {"files_indexed": 5, "chunks_created": 20, "files_failed": 0, "graph": {}}
            return {}

        with patch.object(mod, "_run", side_effect=fake_run):
            with patch.object(mod, "_get", side_effect=fake_get):
                with patch.object(mod, "_post", side_effect=fake_post):
                    result = mod.step_rag()

        assert "knowledge" in result.get("healed", [])

    # ------------------------------------------------------------------
    # step_hooks
    # ------------------------------------------------------------------

    def test_step_hooks_all_present(self, tmp_path):
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        with patch.object(mod, "_run", return_value=(0, "")):
            missing = mod.step_hooks()

        assert missing == []

    def test_step_hooks_some_missing(self, tmp_path):
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        # All hooks fail except the first
        run_calls = [0]
        def fake_run(args, timeout=60):
            run_calls[0] += 1
            return (0, "") if run_calls[0] == 1 else (1, "")

        with patch.object(mod, "_run", side_effect=fake_run):
            missing = mod.step_hooks()

        assert len(missing) == 5  # 5 of 6 hooks missing

    # ------------------------------------------------------------------
    # step_mcp_debugger
    # ------------------------------------------------------------------

    def test_step_mcp_debugger_cli_not_found(self, tmp_path):
        mod = self._load_mod(tmp_path)
        with patch.object(mod, "_run", return_value=(127, "")):
            result = mod.step_mcp_debugger()
        assert result == "unknown"

    def test_step_mcp_debugger_not_registered(self, tmp_path):
        mod = self._load_mod(tmp_path)
        with patch.object(mod, "_run", return_value=(0, "some-other-mcp\nother-mcp")):
            result = mod.step_mcp_debugger()
        assert result == "missing"

    def test_step_mcp_debugger_connected(self, tmp_path):
        mod = self._load_mod(tmp_path)
        with patch.object(mod, "_run", return_value=(0, "mcp-debugger connected ✓")):
            result = mod.step_mcp_debugger()
        assert result == "connected"

    def test_step_mcp_debugger_unhealthy(self, tmp_path):
        mod = self._load_mod(tmp_path)
        with patch.object(mod, "_run", return_value=(0, "mcp-debugger registered but offline")):
            result = mod.step_mcp_debugger()
        assert result == "unhealthy"

    # ------------------------------------------------------------------
    # main() — full verify flow
    # ------------------------------------------------------------------

    def test_main_verify_flow(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        rag_result = {"ready": True, "healed": []}

        with patch("sys.argv", ["boost-run.py", "verify"]):
            with patch.object(mod, "_write_injection"):
                with patch.object(mod, "step_banner"):
                    with patch.object(mod, "step_privacy"):
                        with patch.object(mod, "step_rag", return_value=rag_result):
                            with patch.object(mod, "step_hooks", return_value=[]):
                                with patch.object(mod, "step_rules", return_value=True):
                                    with patch.object(mod, "step_mode", return_value="CONSULT"):
                                        with patch.object(mod, "step_mcp_debugger", return_value="connected"):
                                            with patch.object(mod, "step_workspaces", return_value=[]):
                                                with patch.object(mod, "_run", return_value=(0, "done banner\n")):
                                                    rc = mod.main()

        assert rc == 0

    def test_main_verify_rag_not_ready_skips_done_banner(self, tmp_path):
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)

        rag_result = {"ready": False, "healed": []}

        with patch("sys.argv", ["boost-run.py", "verify"]):
            with patch.object(mod, "_write_injection"):
                with patch.object(mod, "step_banner"):
                    with patch.object(mod, "step_privacy"):
                        with patch.object(mod, "step_rag", return_value=rag_result):
                            with patch.object(mod, "step_hooks", return_value=["PreToolUse"]):
                                with patch.object(mod, "step_rules", return_value=False):
                                    with patch.object(mod, "step_mode", return_value="AUTO"):
                                        with patch.object(mod, "step_mcp_debugger", return_value="missing"):
                                            with patch.object(mod, "step_workspaces", return_value=["task-x"]):
                                                rc = mod.main()

        assert rc == 0  # verify always exits 0
