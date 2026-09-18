"""Does _can_add_a_registry_entry catch every way a function adds to a dict?

That helper is what earns a place on _REMOVAL_ONLY_WRITERS in
test_exec_routes_require_registered_project.py: it has to fail loudly the day
an allowlisted "removal only" writer (currently
indexing.py:_remove_from_project_registry) grows the ability to add an entry
to state/projects.json, the file that gates the exec routes.

Each case below really does add a key when it runs, and none of them is a
subscript assignment, ``.update`` or ``.setdefault``. A checker that only
knows those three spellings passes all of them, which is how the
self-registration hole reopens with every test still green.

The last test is the other half: a checker made sound by answering True to
everything protects nothing either.
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_exec_routes_require_registered_project import _can_add_a_registry_entry  # noqa: E402

_CASES = {
    "dict-merge reassignment (registry = {**registry, k: v})": '''
def _remove_from_project_registry(project_path):
    registry = {}
    registry = {**registry, "new-pid": {"project_path": project_path}}
    return list(registry)
''',
    "dict.__setitem__(registry, k, v)": '''
def _remove_from_project_registry(project_path):
    registry = {}
    dict.__setitem__(registry, "new-pid", {"project_path": project_path})
    return list(registry)
''',
    "operator.setitem(registry, k, v)": '''
import operator
def _remove_from_project_registry(project_path):
    registry = {}
    operator.setitem(registry, "new-pid", {"project_path": project_path})
    return list(registry)
''',
}


@pytest.mark.parametrize("label", list(_CASES))
def test_the_checker_catches_every_real_way_to_add_an_entry(label):
    src = _CASES[label]
    tree = ast.parse(src)
    func_node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

    # Prove the function really does add an entry when it runs, independent
    # of what the static checker says about it.
    ns: dict = {}
    exec(compile(tree, "<adversarial>", "exec"), ns)  # noqa: S102 - test-only, fixed source
    added = ns["_remove_from_project_registry"]("C:/some/path")
    assert added == ["new-pid"], f"{label}: sanity check, the function should have added a key"

    verdict = _can_add_a_registry_entry(func_node)
    assert verdict is True, (
        f"_can_add_a_registry_entry has a false negative for: {label}. "
        f"It returned False for a function that demonstrably adds a "
        f"registry entry, so a removal-only allowlist entry written this "
        f"way would pass test_a_removal_only_writer_really_cannot_add "
        f"while actually being able to self-register a project."
    )


def test_a_function_that_only_removes_still_reads_as_add_free():
    """Answering True to everything would satisfy the cases above and say
    nothing. A real remover has to stay on the clean side of the check."""
    src = '''
def _remove_from_project_registry(project_path):
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    dropped = []
    for pid, entry in list(registry.items()):
        if (entry or {}).get("project_path") == project_path:
            del registry[pid]
            dropped.append(pid)
    return dropped
'''
    tree = ast.parse(src)
    func_node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

    assert _can_add_a_registry_entry(func_node) is False, (
        "the check now reports every function as able to add, so the removal "
        "only allowlist is unearnable and the rule it enforces is dead"
    )
