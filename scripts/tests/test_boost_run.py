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
            if path == "/index-project":
                return {"files_indexed": 50, "chunks_created": 200, "files_failed": 0, "graph": {"resolved": 10, "edges": 8}}
            return {}

        with patch.object(mod, "_run", side_effect=fake_run):
            with patch.object(mod, "_get", side_effect=fake_get):
                with patch.object(mod, "_post", side_effect=fake_post):
                    result = mod.step_rag()

        assert result.get("ready") is True
        assert result.get("healed") == []

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

    # Fixtures below use the real `claude mcp list` shape — a header line then
    # `<name>: <command-or-url> - <status>` per server — because that is what
    # the CLI actually prints. They used to use an invented single-line shape
    # ("mcp-debugger connected ✓") that no `claude mcp list` ever emits, and
    # they only covered one of the four expected servers, so both the connected
    # and unhealthy cases reported "missing" and failed.
    def test_step_mcp_debugger_not_registered(self, tmp_path):
        mod = self._load_mod(tmp_path)
        listed = "Checking MCP server health…\n\nsome-other-mcp: npx -y x - ✔ Connected"
        with patch.object(mod, "_run", return_value=(0, listed)):
            result = mod.step_mcp_debugger()
        assert result == "missing"

    def test_step_mcp_debugger_connected(self, tmp_path):
        mod = self._load_mod(tmp_path)
        listed = "\n".join(
            f"{name}: npx -y {name} - ✔ Connected" for name, _ in mod.MCP_SERVERS_EXPECTED)
        with patch.object(mod, "_run", return_value=(0, listed)):
            result = mod.step_mcp_debugger()
        assert result == "connected"

    def test_step_mcp_debugger_unhealthy(self, tmp_path):
        mod = self._load_mod(tmp_path)
        listed = "\n".join(
            f"{name}: npx -y {name} - ✗ Failed to connect"
            for name, _ in mod.MCP_SERVERS_EXPECTED)
        with patch.object(mod, "_run", return_value=(0, listed)):
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


# ---------------------------------------------------------------------------
# Additional tests for previously uncovered lines
# ---------------------------------------------------------------------------

class TestBoostRunUncoveredLines:
    """Targeted tests for lines 85-86, 130, 132-133, 149-150, 165-166,
    176-177, 188-189, 195-196, 227-228, 232, 261, 264-265."""

    def _load_mod(self, tmp_path):
        import uuid
        mod_name = f"boost_run_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(mod_name, SCRIPTS_DIR / "boost-run.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.STATE = tmp_path / "state"
        mod.BOOST_HOME = tmp_path
        return mod

    # ------------------------------------------------------------------
    # Lines 85-86: cache-clearing loop when __pycache__ dirs exist
    # ------------------------------------------------------------------

    def test_step_banner_clears_pycache(self, tmp_path):
        """step_banner should shutil.rmtree each __pycache__ dir found."""
        mod = self._load_mod(tmp_path)
        mod.BOOST_HOME = tmp_path

        # Create a fake clean-rag/__pycache__ dir so rglob finds it
        pycache = tmp_path / "clean-rag" / "subpkg" / "__pycache__"
        pycache.mkdir(parents=True)

        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        cleared = []

        import shutil as _shutil

        original_rmtree = _shutil.rmtree

        def spy_rmtree(path, ignore_errors=False):
            cleared.append(path)
            original_rmtree(path, ignore_errors=ignore_errors)

        with patch.object(mod, "_run", return_value=(0, "")):
            with patch("shutil.rmtree", side_effect=spy_rmtree):
                mod.step_banner()

        assert len(cleared) >= 1

    # ------------------------------------------------------------------
    # Line 130: warmup returned ready=False
    # ------------------------------------------------------------------

    def test_step_rag_sentinel_write_failure(self, tmp_path):
        """If sentinel .touch() raises, should print a warning and continue."""
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        status_resp = {
            "status": "ready",
            "model": "m",
            "embedding_dimensions": 384,
            "collections": {"knowledge": {}, "agents": {}},
            "dimension_mismatch": [],
        }

        def fake_get(path, timeout=5):
            return status_resp

        def fake_post(path, body, timeout=300):
            if path == "/warmup":
                return {"ready": True}
            if path == "/context":
                return {"total_tokens_approx": 0, "sources_used": 0}
            if path == "/index-project":
                return {"files_indexed": 0, "chunks_created": 0, "files_failed": 0, "graph": {}}
            return {}

        # Patch _temp_dir to return a path whose .touch() will fail
        bad_path = MagicMock()
        bad_path.__truediv__ = MagicMock(return_value=MagicMock(touch=MagicMock(side_effect=OSError("read-only"))))

        import io
        buf = io.StringIO()

        with patch.object(mod, "_run", return_value=(0, "started")):
            with patch.object(mod, "_get", side_effect=fake_get):
                with patch.object(mod, "_post", side_effect=fake_post):
                    with patch.object(mod, "_temp_dir", return_value=bad_path):
                        with patch("sys.stdout", buf):
                            result = mod.step_rag()

        output = buf.getvalue()
        assert "sentinel write failed" in output
        assert result.get("ready") is True

    # ------------------------------------------------------------------
    # Lines 165-166: mismatch rebuild FAILED branch
    # ------------------------------------------------------------------

    def test_step_rag_self_index_stored_in_result(self, tmp_path):
        """Successful self-index stores idx in out['self_index']."""
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        status_resp = {
            "status": "ready",
            "model": "m",
            "embedding_dimensions": 384,
            "collections": {"knowledge": {}, "agents": {}},
            "dimension_mismatch": [],
        }

        idx_result = {"files_indexed": 42, "chunks_created": 99, "files_failed": 0, "graph": {"resolved": 5, "edges": 4}}

        post_call_num = [0]

        def fake_post(path, body, timeout=300):
            post_call_num[0] += 1
            if path == "/warmup":
                return {"ready": True}
            if path == "/context":
                return {"total_tokens_approx": 0, "sources_used": 0}
            if path == "/index-project" and body.get("project_path"):
                return idx_result
            if path == "/index-project":
                return {"files_indexed": 0, "chunks_created": 0, "files_failed": 0, "graph": {}}
            return {}

        with patch.object(mod, "_run", return_value=(0, "started")):
            with patch.object(mod, "_get", return_value=status_resp):
                with patch.object(mod, "_post", side_effect=fake_post):
                    result = mod.step_rag()

        assert result.get("self_index") == idx_result

    def test_step_rag_self_index_fails(self, tmp_path):
        """Self-index POST raises — should print FAILED."""
        (tmp_path / "state").mkdir(parents=True)
        mod = self._load_mod(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)

        status_resp = {
            "status": "ready",
            "model": "m",
            "embedding_dimensions": 384,
            "collections": {"knowledge": {}, "agents": {}},
            "dimension_mismatch": [],
        }

        def fake_post(path, body, timeout=300):
            if path == "/warmup":
                return {"ready": True}
            if path == "/context":
                return {"total_tokens_approx": 0, "sources_used": 0}
            if path == "/index-project" and body.get("project_path"):
                raise OSError("no space left")
            if path == "/index-project":
                return {"files_indexed": 0, "chunks_created": 0, "files_failed": 0, "graph": {}}
            return {}

        import io
        buf = io.StringIO()

        with patch.object(mod, "_run", return_value=(0, "started")):
            with patch.object(mod, "_get", return_value=status_resp):
                with patch.object(mod, "_post", side_effect=fake_post):
                    with patch("sys.stdout", buf):
                        result = mod.step_rag()

        assert "index(self): FAILED" in buf.getvalue()

    # ------------------------------------------------------------------
    # Lines 195-196: memories index success and failure
    # ------------------------------------------------------------------

    def test_step_mode_bad_json_defaults_to_consult(self, tmp_path):
        """Corrupt mode file should fall back to CONSULT gracefully."""
        (tmp_path / "state").mkdir(parents=True)
        (tmp_path / "state" / "claudeboost-mode.json").write_text(
            "NOT VALID JSON!!!", encoding="utf-8"
        )
        mod = self._load_mod(tmp_path)
        mode = mod.step_mode()
        assert mode == "CONSULT"

    # ------------------------------------------------------------------
    # Line 232: session-approvals.json reset when file exists
    # ------------------------------------------------------------------

    def test_step_mode_resets_session_approvals(self, tmp_path):
        """Existing session-approvals.json is reset to empty approvals."""
        (tmp_path / "state").mkdir(parents=True)
        sa_path = tmp_path / "state" / "session-approvals.json"
        sa_path.write_text(
            json.dumps({"sessionId": "abc", "approvals": ["some-approval"]}),
            encoding="utf-8",
        )
        mod = self._load_mod(tmp_path)
        mod.step_mode()

        data = json.loads(sa_path.read_text(encoding="utf-8"))
        assert data["approvals"] == []
        assert data["sessionId"] == ""

    # ------------------------------------------------------------------
    # Line 261: context.md read path (non-empty workspace with status)
    # ------------------------------------------------------------------

    def test_step_workspaces_reads_context_text(self, tmp_path):
        """Workspace with 'blocked' in context.md is detected as active."""
        ws = tmp_path / "workspace" / "task-blocked"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text(
            "## Status\nblocked waiting for API key", encoding="utf-8"
        )
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert "task-blocked" in active

    def test_step_workspaces_implemented_status(self, tmp_path):
        """Workspace with 'implemented' in context.md is detected as active."""
        ws = tmp_path / "workspace" / "task-impl"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text(
            "Status: implemented feature X", encoding="utf-8"
        )
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert "task-impl" in active

    def test_step_workspaces_plan_ready_status(self, tmp_path):
        """Workspace with 'plan_ready' in context.md is detected as active."""
        ws = tmp_path / "workspace" / "task-plan"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text(
            "plan_ready — awaiting implementation", encoding="utf-8"
        )
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert "task-plan" in active

    # ------------------------------------------------------------------
    # Lines 264-265: workspace directory without context.md (skip),
    # and context.md with no matching status keyword (inactive)
    # ------------------------------------------------------------------

    def test_step_workspaces_skips_dir_without_context(self, tmp_path):
        """Workspace folder without context.md is skipped."""
        ws = tmp_path / "workspace" / "task-no-ctx"
        ws.mkdir(parents=True)
        # No context.md created
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert "task-no-ctx" not in active

    def test_step_workspaces_inactive_status_not_included(self, tmp_path):
        """Workspace with no matching keyword is not in active list."""
        ws = tmp_path / "workspace" / "task-done"
        ws.mkdir(parents=True)
        (ws / "context.md").write_text(
            "## Status\ncompleted", encoding="utf-8"
        )
        mod = self._load_mod(tmp_path)
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            active = mod.step_workspaces()
        assert "task-done" not in active

    def test_step_workspaces_read_error_skips_entry(self, tmp_path):
        """When read_text raises on a context.md, the entry is skipped (lines 264-265)."""
        ws = tmp_path / "workspace" / "task-unreadable"
        ws.mkdir(parents=True)
        ctx_path = ws / "context.md"
        # Write the file so is_file() returns True, then patch Path.read_text to raise
        ctx_path.write_text("in progress", encoding="utf-8")

        mod = self._load_mod(tmp_path)

        from pathlib import Path as _Path

        original_read_text = _Path.read_text

        def selective_read_text(self_path, encoding="utf-8", errors="replace"):
            # Only raise for context.md files inside our workspace
            if self_path.name == "context.md":
                raise PermissionError("access denied")
            return original_read_text(self_path, encoding=encoding, errors=errors)

        with patch("pathlib.Path.read_text", selective_read_text):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                # Should not raise — the except branch continues
                active = mod.step_workspaces()

        # Unreadable context is skipped, not added to active
        assert "task-unreadable" not in active
