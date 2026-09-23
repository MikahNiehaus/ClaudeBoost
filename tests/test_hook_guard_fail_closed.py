"""A safety guard must not spell "I crashed" the same way it spells "allowed".

Claude Code reads exit 2 from a PreToolUse hook as block and every other
non-zero code as a non-blocking error. So a guard that dies on a traceback
exits 1 and the tool call it was written to stop goes through.

That happened. verify-loop-git-guard.py annotated a return as `str | None`
(PEP 604, 3.10+) without `from __future__ import annotations`, so under macOS's
system python 3.9.6 the annotation was evaluated at def time and raised
TypeError. The registration in bad-cop.md/good-cop.md falls back to whatever
`python3` is on PATH when $CLAUDEBOOST_PYTHON is unset or stale, which on a
fresh machine is exactly that 3.9. `git push origin main` was not blocked.

Two halves are pinned here:

  1. Nothing under clean-rag/hooks/ may carry an annotation its own fallback
     interpreter cannot evaluate. PEP 563 (`from __future__ import annotations`)
     is how the rest of this repo already handles it -- 116 files do. The floor
     is 3.9: it is what macOS ships via the Xcode CLT, so it is what the
     `elif command -v python3` branch actually selects on a fresh machine.
  2. hook-run.py --fail-closed turns "present but did not reach a verdict"
     into block, so the next instance of this class fails loudly instead of
     silently allowing.

Run: python -m pytest tests/test_hook_guard_fail_closed.py -v
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO / "clean-rag" / "hooks"
HOOK_RUN = REPO / "clean-rag" / "portable" / "hook-run.py"

ALLOW = 0
BLOCK = 2

PUSH_PAYLOAD = json.dumps(
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}})
STATUS_PAYLOAD = json.dumps(
    {"tool_name": "Bash", "tool_input": {"command": "git status"}})

# Scrubbed, not inherited: these hooks must work with CLEAN_RAG_HOME,
# CLAUDEBOOST_HOME and CLAUDEBOOST_PYTHON all absent.
SCRUBBED_ENV = {"PATH": "/usr/bin:/bin"}


def _run(args, payload, env=None):
    return subprocess.run(
        [sys.executable, str(HOOK_RUN), *args],
        input=payload,
        capture_output=True,
        text=True,
        env=dict(env if env is not None else SCRUBBED_ENV),
    )


# ── half 1: no hook may use syntax its fallback interpreter cannot evaluate ──


def _uses_pep604_annotations(tree: ast.AST) -> bool:
    """Does any annotation need Python 3.10+ to be *evaluated*?

    Only PEP 604 (`str | None`, a BinOp with BitOr) does. PEP 585's
    `tuple[bool, str]` looks similar but landed in 3.9, so it is fine on the
    floor below and is deliberately not flagged -- verifier_state.py,
    research_state.py, research-gate.py and high_stakes.py all use it and all
    import cleanly on 3.9.6.

    Annotations on a module-level def are evaluated at import time, so this is
    an import-time crash, not a typing nicety.
    """
    def offending(node) -> bool:
        return any(
            isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
            for sub in ast.walk(node)
        )

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            annotations = [a.annotation for a in node.args.args if a.annotation]
            annotations += [a.annotation for a in node.args.kwonlyargs if a.annotation]
            if node.returns:
                annotations.append(node.returns)
            if any(offending(a) for a in annotations):
                return True
        elif isinstance(node, ast.AnnAssign) and node.annotation:
            if offending(node.annotation):
                return True
    return False


def _has_future_annotations(tree: ast.AST) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize(
    "script", sorted(HOOKS_DIR.glob("*.py")), ids=lambda p: p.name)
def test_hook_annotations_survive_an_old_fallback_interpreter(script):
    tree = ast.parse(script.read_text(encoding="utf-8"))
    if not _uses_pep604_annotations(tree):
        return
    assert _has_future_annotations(tree), (
        f"{script.name} evaluates a 3.10+ annotation at import time. The hook "
        "registrations fall back to whatever python3 is on PATH, which can be "
        "3.9. Add `from __future__ import annotations` (PEP 563)."
    )


# ── half 2: --fail-closed turns "no verdict" into block ─────────────────────


@pytest.fixture()
def guard(tmp_path):
    """A stand-in guard whose exit code the test chooses."""
    def make(body: str) -> Path:
        path = tmp_path / "guard.py"
        path.write_text(body, encoding="utf-8")
        return path
    return make


def test_crashing_guard_blocks_under_fail_closed(guard):
    script = guard("raise RuntimeError('guard is broken')\n")
    assert _run(["--fail-closed", str(script)], PUSH_PAYLOAD).returncode == BLOCK


def test_crashing_guard_still_passes_its_code_through_without_the_flag(guard):
    """The default stays exactly as it was; only opted-in guards fail closed."""
    script = guard("raise RuntimeError('guard is broken')\n")
    assert _run([str(script)], PUSH_PAYLOAD).returncode == 1


def test_guard_that_allows_is_not_turned_into_a_block(guard):
    script = guard("import sys\nsys.exit(0)\n")
    assert _run(["--fail-closed", str(script)], STATUS_PAYLOAD).returncode == ALLOW


def test_guard_that_blocks_still_blocks(guard):
    script = guard("import sys\nsys.exit(2)\n")
    assert _run(["--fail-closed", str(script)], PUSH_PAYLOAD).returncode == BLOCK


def test_missing_script_still_allows_so_a_branch_switch_cannot_brick_claude(tmp_path):
    """hook-run.py's core contract, unchanged: absence is a no-op, not a block."""
    missing = tmp_path / "not-on-this-branch.py"
    assert _run(["--fail-closed", str(missing)], PUSH_PAYLOAD).returncode == ALLOW


def test_fail_closed_explains_itself_on_stderr(guard):
    script = guard("raise RuntimeError('guard is broken')\n")
    result = _run(["--fail-closed", str(script)], PUSH_PAYLOAD)
    assert "BLOCKED" in result.stderr
    assert "could not run" in result.stderr


# ── the real guard, through the real runner, on a scrubbed environment ──────


@pytest.mark.parametrize("payload,expected", [
    (PUSH_PAYLOAD, BLOCK),
    (STATUS_PAYLOAD, ALLOW),
])
def test_the_real_git_guard_decides_correctly_through_hook_run(payload, expected):
    guard_path = HOOKS_DIR / "verify-loop-git-guard.py"
    assert _run(["--fail-closed", str(guard_path)], payload).returncode == expected


# ── the wiring, so the flag cannot be dropped from the registrations ────────


@pytest.mark.parametrize("agent,guard_name", [
    ("bad-cop.md", "verify-loop-git-guard.py"),
    ("good-cop.md", "verify-loop-git-guard.py"),
    ("quick-cop.md", "quick-cop-bash-guard.py"),
])
def test_guard_registrations_ask_for_fail_closed(agent, guard_name):
    text = (REPO / "clean-rag" / "portable" / "agents" / agent).read_text(
        encoding="utf-8")
    command = next(line for line in text.splitlines() if "command:" in line)
    assert guard_name in command
    # every interpreter branch, not just the first
    assert command.count("hook-run.py") == command.count("--fail-closed") == 4
    # the final `py` branch is the one with no `command -v` in front of it, so
    # a missing launcher there would exit 127 and read as allowed
    assert "|| exit 2" in command


# ── the opt-in must stay opt-in ─────────────────────────────────────────────


def _load_hook_run():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hook_run_module", HOOK_RUN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fail_closed,expected", [(False, ALLOW), (True, BLOCK)])
def test_a_launcher_failure_only_blocks_when_fail_closed_was_asked_for(
        fail_closed, expected):
    """subprocess.run itself raising is the one path not reachable through the
    CLI, and getting it wrong is expensive in both directions: blocking here
    without the flag would brick every Edit/Write hook on a bad launcher, which
    is the exact failure hook-run.py was written to prevent.
    """
    hook_run = _load_hook_run()
    assert hook_run._undecided(
        Path("guard.py"), "OSError: bad launcher", fail_closed) == expected
