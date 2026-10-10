"""The console-less server must start every child with NO_WINDOW.

Otherwise Windows flashes a console each sweep when `git check-ignore` runs.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

from server import config, file_scan  # noqa: E402

SERVER = CLEAN_RAG / "server"
SPAWNERS = {"run", "Popen", "check_output", "check_call", "call"}
# graphrag_client opens a console on purpose so the overnight build can be watched.
DELIBERATELY_VISIBLE = {"graphrag_client.py"}


def _spawn_calls(tree):
    module_names, direct_names = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            module_names |= {a.asname or a.name for a in node.names if a.name == "subprocess"}
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            direct_names |= {a.asname or a.name for a in node.names if a.name in SPAWNERS}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in SPAWNERS
                and isinstance(func.value, ast.Name) and func.value.id in module_names):
            yield node
        elif isinstance(func, ast.Name) and func.id in direct_names:
            yield node


def _binds_no_window(tree):
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and any(
                (a.asname or a.name) == "NO_WINDOW" for a in node.names):
            return True
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "NO_WINDOW" for t in node.targets):
            return True
    return False


def _server_trees():
    for path in sorted(SERVER.glob("*.py")):
        if path.name not in DELIBERATELY_VISIBLE:
            yield path, ast.parse(path.read_text(encoding="utf-8"))


def test_every_server_subprocess_call_hides_its_window():
    missing = []
    for path, tree in _server_trees():
        for call in _spawn_calls(tree):
            flags = [k for k in call.keywords if k.arg == "creationflags"]
            if not flags or ast.unparse(flags[0].value) != "NO_WINDOW":
                missing.append(f"{path.name}:{call.lineno}")
    assert not missing, f"subprocess calls without creationflags=NO_WINDOW: {missing}"


def test_every_module_using_no_window_binds_it():
    # A missing import is a NameError at spawn time, which callers may swallow.
    unbound = [
        path.name for path, tree in _server_trees()
        if any(isinstance(n, ast.Name) and n.id == "NO_WINDOW" for n in ast.walk(tree))
        and not _binds_no_window(tree)
    ]
    assert not unbound, f"NO_WINDOW used but never imported or assigned in: {unbound}"


def test_the_scan_finds_at_least_the_known_call_sites():
    found = sum(1 for _, tree in _server_trees() for _ in _spawn_calls(tree))
    assert found >= 6


def test_no_window_is_the_windows_flag_and_zero_elsewhere():
    if sys.platform == "win32":
        assert config.NO_WINDOW == subprocess.CREATE_NO_WINDOW
    else:
        assert config.NO_WINDOW == 0


def test_git_check_ignore_is_spawned_without_a_window(tmp_path, monkeypatch):
    seen = {}

    def fake_run(*args, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(args, 1, b"", b"")

    monkeypatch.setattr(file_scan.subprocess, "run", fake_run)
    assert file_scan._git_ignored(tmp_path, ["a.py"]) == set()
    assert seen["creationflags"] == config.NO_WINDOW


@pytest.mark.skipif(sys.platform != "win32", reason="the flag only exists on Windows")
def test_real_git_still_answers_with_the_flag(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True,
                   creationflags=config.NO_WINDOW)
    (tmp_path / ".gitignore").write_text("skip.py\n")
    assert file_scan._git_ignored(tmp_path, ["skip.py", "keep.py"]) == {"skip.py"}
