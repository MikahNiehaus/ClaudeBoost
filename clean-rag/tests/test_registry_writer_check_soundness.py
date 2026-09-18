"""bad-cop adversarial test: does _can_add_a_registry_entry actually catch
every way a function can put an entry into a dict?

test_exec_routes_require_registered_project.py's own docstring for this
helper says it is meant to fail loudly the day an allowlisted "removal only"
writer (currently indexing.py:_remove_from_project_registry) grows the
ability to add an entry to state/projects.json, the file that gates the exec
routes. It only recognises three shapes: a subscript assignment
(``d[k] = v``), ``.update(...)``, and ``.setdefault(...)``.

This proves three other ways to put a key into a dict that the checker does
not recognise at all, and that all three really do add the entry when run.
A future edit to the allowlisted function using any of these forms would
pass test_a_removal_only_writer_really_cannot_add while silently reopening
the self-registration hole that whole test class exists to prevent.
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
def test_checker_misses_a_real_way_to_add_an_entry(label):
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
    # This is the actual bug: the checker says False (cannot add) for code
    # that we just proved DOES add an entry.
    assert verdict is True, (
        f"_can_add_a_registry_entry has a false negative for: {label}. "
        f"It returned False for a function that demonstrably adds a "
        f"registry entry, so a removal-only allowlist entry written this "
        f"way would pass test_a_removal_only_writer_really_cannot_add "
        f"while actually being able to self-register a project."
    )
