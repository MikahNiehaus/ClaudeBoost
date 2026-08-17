"""Adversarial tests for the QA tooling additions in install.py.

Covers:
- install_npm_qa_tools(): best-effort, idempotent, npm-absent, timeout,
  subprocess failure, --skip-deps guard
- register_lint_gate_hook(): sentinel at module level, hook pattern, idempotent
- requirements.txt: lizard version range, mutatest constraint
- bad-cop.md / good-cop.md: no new mcp__* in prose without frontmatter entry
- axe-core JS script: valid syntax, IIFE, missing onerror documented
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager, ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1] / "clean-rag"
INSTALL_PY = CLEAN_RAG / "install.py"
PORTABLE_AGENTS = CLEAN_RAG / "portable" / "agents"
REQUIREMENTS_TXT = CLEAN_RAG / "requirements.txt"


def _load_install():
    spec = importlib.util.spec_from_file_location("install_mod", INSTALL_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


install = _load_install()


def _all_main_hooks_noop(install_mod, extra=None):
    """Return an ExitStack that patches all main() callees to noop,
    except those listed in extra (which override with their own side_effect)."""
    noop = lambda: None
    names = [
        "install_deps", "install_npm_qa_tools", "install_user_assets",
        "ensure_directories", "ensure_env_file", "wipe_clean_rag_hooks",
        "register_research_gate_hook", "register_research_gate_bash_hook",
        "register_research_record_hook", "register_graph_context_hook",
        "set_env_var", "protect_research_state", "register_session_prompt",
        "register_rag_enforce_hook", "register_reindex_hook",
        "register_verify_after_edit_hook", "register_record_edit_hook",
        "setup_graphrag", "setup_gpu_memory_manager",
        "register_spec_compliance_gate_hook", "register_auto_test_gate_hook",
        "register_verifier_gate_hook", "register_verifier_record_hook",
        "register_lint_gate_hook", "configure_web_search_env",
        "configure_metrics_env", "register_code_pattern_inject_hook",
        "configure_code_pattern_inject_env", "heal_stale_hooks",
    ]
    stack = ExitStack()
    extra = extra or {}
    for name in names:
        if name in extra:
            stack.enter_context(
                patch.object(install_mod, name, side_effect=extra[name])
            )
        else:
            stack.enter_context(patch.object(install_mod, name, noop))
    return stack


# ===========================================================================
# Property 1: install_npm_qa_tools()
# ===========================================================================

class TestInstallNpmQaTools:

    def test_no_npm_warns_and_returns_without_raising(self, capsys):
        with patch("shutil.which", return_value=None):
            install.install_npm_qa_tools()
        out = capsys.readouterr().out
        assert "npm" in out.lower(), "No npm warning emitted: " + repr(out)

    def test_binary_already_present_skips_install(self):
        def _which(name):
            if name == "npm":
                return "/usr/bin/npm"
            return f"/usr/bin/{name}"

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run") as mock_run:
            install.install_npm_qa_tools()

        assert mock_run.call_count == 0, (
            f"subprocess.run called {mock_run.call_count}x even though binaries on PATH"
        )

    def test_timeout_expired_caught_not_raised(self, capsys):
        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd=["npm"], timeout=120)):
            install.install_npm_qa_tools()

        out = capsys.readouterr().out
        assert "failed" in out.lower() or "warn" in out.lower(), (
            "No warning on TimeoutExpired: " + repr(out)
        )

    def test_nonzero_exit_continues_to_second_tool(self):
        """A failure on the first tool must not abort the loop — second tool must run."""
        call_count = [0]

        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        def _run(cmd, **kw):
            call_count[0] += 1
            r = MagicMock()
            r.returncode = 1
            r.stderr = "error"
            return r

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run", side_effect=_run):
            install.install_npm_qa_tools()

        assert call_count[0] == 2, (
            f"Expected 2 subprocess calls, got {call_count[0]}. "
            "Loop breaks on first failure — second tool skipped silently."
        )

    def test_hardcoded_packages_in_command(self):
        captured = []

        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        def _run(cmd, **kw):
            captured.append(list(cmd))
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run", side_effect=_run):
            install.install_npm_qa_tools()

        assert len(captured) == 2
        packages = {cmd[3] for cmd in captured}
        assert packages == {"odiff-bin", "jscpd@5"}, (
            f"Unexpected packages: {packages}"
        )

    def test_timeout_is_120(self):
        timeouts = []

        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        def _run(cmd, **kw):
            timeouts.append(kw.get("timeout", "MISSING"))
            r = MagicMock()
            r.returncode = 0
            return r

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run", side_effect=_run):
            install.install_npm_qa_tools()

        assert all(t == 120 for t in timeouts), (
            f"timeout values {timeouts} — must be 120"
        )

    def test_skip_deps_skips_npm_install(self):
        called = []
        with _all_main_hooks_noop(install, extra={
            "install_npm_qa_tools": lambda: called.append(1),
        }), patch("sys.argv", ["install.py", "--skip-deps"]):
            install.main()
        assert called == [], (
            "install_npm_qa_tools() ran with --skip-deps"
        )


# ===========================================================================
# Property 2: register_lint_gate_hook()
# ===========================================================================

class TestRegisterLintGateHook:

    def test_sentinel_at_module_level(self):
        assert hasattr(install, "LINT_GATE_SENTINEL")
        assert install.LINT_GATE_SENTINEL == "lint-gate.py"

    def test_hook_written_to_posttooluse(self, tmp_path):
        fake = tmp_path / "settings.json"
        fake.write_text("{}", encoding="utf-8")
        with patch.object(install, "SETTINGS_PATH", fake):
            install.register_lint_gate_hook()
        data = json.loads(fake.read_text(encoding="utf-8"))
        entries = data.get("hooks", {}).get("PostToolUse", [])
        assert any(
            "lint-gate.py" in h.get("command", "")
            for e in entries
            for h in e.get("hooks", [])
        ), "No PostToolUse entry with lint-gate.py"

    def test_idempotent_no_duplicate(self, tmp_path):
        fake = tmp_path / "settings.json"
        fake.write_text("{}", encoding="utf-8")
        with patch.object(install, "SETTINGS_PATH", fake):
            install.register_lint_gate_hook()
            install.register_lint_gate_hook()
        data = json.loads(fake.read_text(encoding="utf-8"))
        entries = data.get("hooks", {}).get("PostToolUse", [])
        lint = [e for e in entries
                if any("lint-gate.py" in h.get("command", "")
                       for h in e.get("hooks", []))]
        assert len(lint) == 1, f"Got {len(lint)} entries — idempotency broken"

    def test_matcher_covers_edit_write_multiedit(self, tmp_path):
        fake = tmp_path / "settings.json"
        fake.write_text("{}", encoding="utf-8")
        with patch.object(install, "SETTINGS_PATH", fake):
            install.register_lint_gate_hook()
        data = json.loads(fake.read_text(encoding="utf-8"))
        entries = data.get("hooks", {}).get("PostToolUse", [])
        entry = next(
            (e for e in entries
             if any("lint-gate.py" in h.get("command", "")
                    for h in e.get("hooks", []))),
            None
        )
        assert entry is not None
        matcher = entry.get("matcher", "")
        assert "Edit" in matcher and "Write" in matcher, (
            f"matcher '{matcher}' must cover Edit|Write|MultiEdit"
        )

    def test_called_from_main(self):
        called = []
        with _all_main_hooks_noop(install, extra={
            "register_lint_gate_hook": lambda: called.append(True),
        }), patch("sys.argv", ["install.py"]):
            install.main()
        assert called, "register_lint_gate_hook() not called from main()"


# ===========================================================================
# Property 3: requirements.txt
# ===========================================================================

class TestRequirementsTxt:

    def _reqs(self):
        return [l.strip() for l in
                REQUIREMENTS_TXT.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]

    def test_lizard_present(self):
        assert any(r.startswith("lizard") for r in self._reqs()), \
            "lizard not in requirements.txt"

    def test_lizard_lower_bound(self):
        req = next((r for r in self._reqs() if r.startswith("lizard")), None)
        assert req and "1.17" in req, f"Missing >=1.17 in '{req}'"

    def test_lizard_upper_bound_below_2(self):
        req = next((r for r in self._reqs() if r.startswith("lizard")), None)
        assert req and ("<2.0" in req or "<2" in req), \
            f"Missing <2.0 in '{req}'"

    def test_lizard_installed_in_range(self):
        import importlib.metadata
        try:
            v = importlib.metadata.version("lizard")
        except importlib.metadata.PackageNotFoundError:
            pytest.skip("lizard not installed")
        parts = v.split(".")
        major, minor = int(parts[0]), int(parts[1])
        assert (major, minor) >= (1, 17) and major < 2, \
            f"lizard {v} outside [1.17, 2.0)"

    def test_mutatest_present(self):
        reqs = [r for r in self._reqs() if r.startswith("mutatest")]
        assert reqs and "3.0" in reqs[0], \
            f"mutatest >=3.0 not in requirements: {reqs}"


# ===========================================================================
# Property 4/5: mcp__* constraint in agent markdown
# ===========================================================================

class TestAgentMarkdownMcpConstraints:

    def _tools(self, path):
        text = path.read_text(encoding="utf-8")
        in_fm = False
        for line in text.splitlines():
            if line.strip() == "---":
                if not in_fm:
                    in_fm = True
                    continue
                break
            if in_fm and line.startswith("tools:"):
                return {t.strip() for t in line[len("tools:"):].split(",")}
        return set()

    def _section_mcp_refs(self, path, heading):
        """Extract mcp__* refs from a specific ## section, excluding glob stubs.
        Mirrors the scope of tests/test_agent_tool_coverage.py exactly."""
        import re
        text = path.read_text(encoding="utf-8")
        pattern = rf"^## {re.escape(heading)}\s*$"
        lines = text.splitlines()
        in_section = False
        collected = []
        for line in lines:
            if re.match(pattern, line):
                in_section = True
                continue
            if in_section:
                if line.startswith("## "):
                    break
                collected.append(line)
        section = "\n".join(collected)
        # Same pattern as test_agent_tool_coverage.py; skip stubs ending in __
        refs = set(re.findall(r"mcp__[a-zA-Z0-9_]+", section))
        return {r for r in refs if not r.endswith("__")}

    def test_bad_cop_prose_refs_in_frontmatter(self):
        """Mirror of tests/test_agent_tool_coverage.py scope: 'Use the real tools' section."""
        p = PORTABLE_AGENTS / "bad-cop.md"
        refs = self._section_mcp_refs(p, "Use the real tools, not print statements")
        unlisted = refs - self._tools(p)
        assert not unlisted, (
            f"bad-cop.md 'Use the real tools' section mcp__* not in frontmatter: "
            f"{sorted(unlisted)}"
        )

    def test_good_cop_prose_refs_in_frontmatter(self):
        """Mirror of tests/test_agent_tool_coverage.py scope: 'Use the real tools' section."""
        p = PORTABLE_AGENTS / "good-cop.md"
        refs = self._section_mcp_refs(p, "Use the real tools to confirm the fix")
        unlisted = refs - self._tools(p)
        assert not unlisted, (
            f"good-cop.md 'Use the real tools' section mcp__* not in frontmatter: "
            f"{sorted(unlisted)}"
        )

    def test_bad_cop_static_analysis_section_no_mcp(self):
        import re
        text = (PORTABLE_AGENTS / "bad-cop.md").read_text(encoding="utf-8")
        m = re.search(r"## Static analysis tools(.*?)(?=^##|\Z)",
                      text, re.DOTALL | re.MULTILINE)
        assert m, "## Static analysis tools section not found"
        refs = re.findall(r"mcp__\w+", m.group(1))
        assert not refs, f"Static analysis section has mcp__* refs: {refs}"


# ===========================================================================
# Property 6: axe-core injection script
# ===========================================================================

class TestAxeCoreScript:

    def _script(self):
        import re
        text = (PORTABLE_AGENTS / "bad-cop.md").read_text(encoding="utf-8")
        m = re.search(r"```javascript\n(.*?)```", text, re.DOTALL)
        assert m, "No ```javascript block in bad-cop.md"
        return m.group(1).strip()

    def test_valid_js_syntax(self):
        script = self._script()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js',
                                         delete=False, encoding='utf-8') as f:
            f.write(script)
            fname = f.name
        try:
            r = subprocess.run(["node", "--check", fname],
                               capture_output=True, text=True, timeout=10)
            assert r.returncode == 0, f"Syntax error:\n{r.stderr}"
        finally:
            os.unlink(fname)

    def test_is_iife(self):
        script = self._script()
        assert script.startswith("(async ()"), \
            f"Not an async IIFE: {script[:40]!r}"
        assert script.rstrip().endswith("()"), \
            f"Not invoked: {script[-20:]!r}"

    def test_missing_onerror_documented(self):
        """onerror is absent — Promise hangs if CDN unreachable.
        This assertion documents the deficiency. Flip it when fixed."""
        script = self._script()
        assert "onerror" not in script, (
            "onerror handler added — update this test to verify it's correct"
        )

    def test_loads_from_external_cdn(self):
        """CDN load is present — violates localhost-only when CSP blocks external scripts."""
        assert "cdn.jsdelivr.net" in self._script()


# ===========================================================================
# Mutation kill tests
# ===========================================================================

class TestMutantKills:

    def test_kill_ROR_returncode_check(self):
        """returncode==0 check: success must _ok, not _warn."""
        ok_msgs, warn_msgs = [], []

        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        def _run(cmd, **kw):
            r = MagicMock(); r.returncode = 0; r.stderr = ""; return r

        with patch.object(install, "_ok", side_effect=ok_msgs.append), \
             patch.object(install, "_warn", side_effect=warn_msgs.append), \
             patch("shutil.which", side_effect=_which), \
             patch("subprocess.run", side_effect=_run):
            install.install_npm_qa_tools()

        assert not [m for m in warn_msgs if "install failed" in m], \
            f"False 'install failed' warn on success: {warn_msgs}"
        assert [m for m in ok_msgs if "installed" in m.lower()], \
            f"No 'installed' _ok on success: {ok_msgs}"

    def test_kill_SIR_timeout_exactly_120(self):
        """timeout=120 must not be removed."""
        timeouts = []

        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        def _run(cmd, **kw):
            timeouts.append(kw.get("timeout", None))
            r = MagicMock(); r.returncode = 0; return r

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run", side_effect=_run):
            install.install_npm_qa_tools()

        assert all(t == 120 for t in timeouts), \
            f"Unexpected timeouts: {timeouts}"

    def test_kill_COR_loop_runs_both_tools(self):
        """Loop must not short-circuit after first tool."""
        n = [0]

        def _which(name):
            return "/usr/bin/npm" if name == "npm" else None

        def _run(cmd, **kw):
            n[0] += 1
            r = MagicMock(); r.returncode = 0; return r

        with patch("shutil.which", side_effect=_which), \
             patch("subprocess.run", side_effect=_run):
            install.install_npm_qa_tools()

        assert n[0] == 2, f"Expected 2, got {n[0]}"
