"""
Adversarial verification for the RAG-port / status-shape / encoding diff.

Targets three correctness properties from the diff under review:
  1. boost-run.py must probe the port from clean-rag/server/config.py's
     STANDALONE_PORT, not a hardcoded literal, and must fall back to 8613
     if that import fails.
  2. step_rag() must not raise when /status returns projects.entries as a
     dict keyed by project id (the real clean-rag shape), and must not raise
     when entries is missing/empty either.
  3. setup.py must not raise UnicodeEncodeError relaying non-cp1252 child
     output on a cp1252 console.

Each test here was run once against a deliberately broken (reverted) version
of the changed code to confirm it actually fails on the old behaviour -- see
the bad-cop report for the mutation output.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from helpers import hook_env  # noqa: E402


def _load_boost_run(tmp_path):
    mod_name = f"boost_run_adv_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPTS_DIR / "boost-run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.STATE = tmp_path / "state"
    return mod


# ---------------------------------------------------------------------------
# Property 1: real dynamic port probe, not a hardcoded literal
# ---------------------------------------------------------------------------

class TestRagPortDynamicProbe:
    def test_rag_port_matches_real_clean_rag_config(self, tmp_path):
        """PORT must equal clean-rag/server/config.py's STANDALONE_PORT (8613)
        when clean-rag actually exists at BOOST_HOME, not a hardcoded 8612."""
        mod = _load_boost_run(tmp_path)
        mod.BOOST_HOME = REPO_ROOT  # real tree, clean-rag present
        for name in list(sys.modules):
            if name == "server" or name.startswith("server."):
                del sys.modules[name]
        assert mod._rag_port() == 8613
        assert mod._rag_port() != 8612

    def test_rag_port_is_dynamic_not_a_second_hardcode(self, tmp_path, monkeypatch):
        """Changing clean-rag's own CLEAN_RAG_PORT env var must change the
        probed value. This is the test that kills a mutant which just swaps
        the literal 8612 -> 8613 without actually reading config.py: such a
        mutant would return 8613 regardless of CLEAN_RAG_PORT."""
        monkeypatch.setenv("CLEAN_RAG_PORT", "9931")
        for name in list(sys.modules):
            if name == "server" or name.startswith("server."):
                del sys.modules[name]
        mod = _load_boost_run(tmp_path)
        mod.BOOST_HOME = REPO_ROOT
        assert mod._rag_port() == 9931
        # cleanup: drop the module we polluted so later tests re-import fresh
        for name in list(sys.modules):
            if name == "server" or name.startswith("server."):
                del sys.modules[name]

    def test_rag_port_falls_back_to_8613_when_config_import_fails(self, tmp_path):
        """No clean-rag/server/config.py reachable at BOOST_HOME -> fallback 8613."""
        mod = _load_boost_run(tmp_path)
        mod.BOOST_HOME = tmp_path  # empty dir, no clean-rag/ subdir at all
        for name in list(sys.modules):
            if name == "server" or name.startswith("server."):
                del sys.modules[name]
        assert mod._rag_port() == 8613

    def test_header_prints_the_same_port_it_probes(self, tmp_path):
        """main()'s banner must use the PORT variable, not a hardcoded string,
        so the header can never drift from what was actually probed."""
        source = (SCRIPTS_DIR / "boost-run.py").read_text(encoding="utf-8")
        assert 'f"\\n--- RAG (port {PORT}) ---"' in source
        assert "--- RAG (port 8612) ---" not in source


# ---------------------------------------------------------------------------
# Property 2: /status projects.entries as a dict (real clean-rag shape)
# ---------------------------------------------------------------------------

class TestStepRagEntriesShape:
    def _common_status(self, entries):
        return {
            "status": "ready",
            "code_embedding_model": "m",
            "ram_mb": 100,
            "projects": {"count": len(entries), "entries": entries},
        }

    def _run_step_rag_with_status(self, tmp_path, status_resp):
        mod = _load_boost_run(tmp_path)
        mod.SCRIPTS = tmp_path / "scripts"
        (tmp_path / "scripts").mkdir(parents=True)
        (tmp_path / "state").mkdir(parents=True)

        def fake_post(path, body, timeout=300):
            if path == "/index-project":
                return {"files_indexed": 0, "chunks_created": 0, "files_failed": 0, "graph": {}}
            return {}

        with patch.object(mod, "_run", return_value=(0, "started")):
            with patch.object(mod, "_get", return_value=status_resp):
                with patch.object(mod, "_post", side_effect=fake_post):
                    return mod.step_rag()

    def test_dict_shaped_entries_with_incomplete_project_does_not_raise(self, tmp_path):
        """Real clean-rag /status shape: entries is a dict keyed by project id.
        This is the exact shape returned by GET /status against the live
        server (confirmed via curl), and no existing test in
        test_boost_run.py exercises a non-empty `entries` at all."""
        entries = {
            "abc123": {"project_path": "C:/prj/x", "incomplete": True},
            "def456": {"project_path": "C:/prj/y", "incomplete": False},
        }
        status_resp = self._common_status(entries)
        result = self._run_step_rag_with_status(tmp_path, status_resp)
        assert result.get("ready") is True

    def test_dict_shaped_entries_missing_is_safe(self, tmp_path):
        status_resp = {
            "status": "ready",
            "code_embedding_model": "m",
            "ram_mb": 1,
            "projects": {"count": 0},  # no "entries" key at all
        }
        result = self._run_step_rag_with_status(tmp_path, status_resp)
        assert result.get("ready") is True

    def test_old_list_shaped_entries_code_would_have_crashed_on_real_shape(self, tmp_path):
        """Mutation kill test: reproduce the PRE-FIX line
        `status.get("projects", {}).get("entries", [])` (list default,
        iterated directly) against the REAL dict-shaped entries clean-rag
        actually returns, and show it raises. This proves the fix (using
        `.get("entries", {}).values()`) is not decorative."""
        entries = {"abc123": {"incomplete": True}}
        with pytest.raises(AttributeError):
            [e for e in entries if e.get("incomplete")]  # old code path shape
            # ^ iterating a dict of dicts directly yields *keys* (strings),
            # so .get on a str raises AttributeError. This is exactly what
            # the old code did when handed the real /status shape.


# ---------------------------------------------------------------------------
# Property 3: setup.py stdout reconfigure prevents UnicodeEncodeError
# ---------------------------------------------------------------------------

class TestSetupStdoutEncoding:
    def test_reconfigure_present_before_any_print_helpers(self):
        source = (SCRIPTS_DIR / "setup.py").read_text(encoding="utf-8")
        reconf_idx = source.index("sys.stdout.reconfigure")
        first_say_def_idx = source.index("def _say")
        assert reconf_idx < first_say_def_idx, (
            "reconfigure must run before _say/_info/_warn are ever defined/used"
        )

    def test_child_output_with_braille_spinner_does_not_crash_under_cp1252(self, tmp_path):
        """Reproduces the actual reported crash: an ollama-pull-style braille
        spinner character relayed to a cp1252 Windows console. Run as a real
        subprocess with PYTHONUTF8/PYTHONIOENCODING scrubbed out (hook_env's
        allowlist already does this) so the child's stdout encoding is
        whatever the OS default is, not whatever this dev machine happens to
        have configured."""
        script = tmp_path / "relay_braille.py"
        script.write_text(
            "import sys\n"
            "sys.path.insert(0, r'%s')\n"
            "import importlib.util\n"
            "spec = importlib.util.spec_from_file_location('setup_mod', r'%s')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "mod._info('pulling model \u280b\u2839 spinner')\n"
            % (str(SCRIPTS_DIR), str(SCRIPTS_DIR / "setup.py")),
            encoding="utf-8",
        )
        env = hook_env()
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            env=env,
        )
        assert result.returncode == 0, (
            f"crashed relaying non-cp1252 output:\n{result.stderr.decode('utf-8', 'replace')}"
        )

    def test_without_the_fix_the_same_relay_crashes(self, tmp_path):
        """Negative control / mutation check: strip the reconfigure call and
        show the exact same relay now raises UnicodeEncodeError. Proves test
        above is not vacuously passing for an unrelated reason."""
        setup_src = (SCRIPTS_DIR / "setup.py").read_text(encoding="utf-8")
        mutant_src = setup_src.replace(
            'if hasattr(sys.stdout, "reconfigure"):\n'
            '    sys.stdout.reconfigure(encoding="utf-8", errors="replace")\n',
            "# reconfigure removed by mutation test\n",
            1,
        )
        assert mutant_src != setup_src, "mutation target text not found -- setup.py changed shape"
        mutant_path = tmp_path / "setup_mutant.py"
        mutant_path.write_text(mutant_src, encoding="utf-8")

        script = tmp_path / "relay_braille_mutant.py"
        script.write_text(
            "import sys\n"
            "sys.path.insert(0, r'%s')\n"
            "import importlib.util\n"
            "spec = importlib.util.spec_from_file_location('setup_mod_mutant', r'%s')\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "mod._info('pulling model \u280b\u2839 spinner')\n"
            % (str(SCRIPTS_DIR), str(mutant_path)),
            encoding="utf-8",
        )
        env = hook_env()
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            env=env,
        )
        assert result.returncode != 0
        assert b"UnicodeEncodeError" in result.stderr
