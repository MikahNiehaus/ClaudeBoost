"""The hooks must load under the oldest Python this project tells people to install.

`install.bat`, `install.sh`, `uninstall.bat`, `uninstall.sh` and setup.py's own
preflight all name "Python 3.9+", so 3.9 is the documented floor and hooks are
plain scripts run by whichever interpreter the hook command line resolves.

A bare `X | Y` annotation is PEP 604 and is evaluated at runtime on 3.9, where
it raises `TypeError: unsupported operand type(s) for |`. That happens while the
module is still being imported, above every `except Exception: sys.exit(0)`
handler these gates wrap their own bodies in, so the fail open design never gets
a chance to run and the hook emits a traceback on every Edit instead of a nudge.
`from __future__ import annotations` (PEP 563) makes annotations strings on
every version and costs nothing, which is why most of this tree already has it.

Checked statically rather than by launching a 3.9 interpreter on purpose. Most
machines that run this suite have exactly one Python, so a test that shelled out
to `py -3.9` would skip itself into uselessness on the machines that most need
it. The AST carries the whole answer, so this test gives the same verdict
everywhere.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# (major, minor) floor, matching scripts/setup.py's MIN_PYTHON.
FLOOR = (3, 9)

# Names that make an `X | Y` read as a type union rather than an arithmetic or
# bitwise expression on real values.
TYPE_NAMES = frozenset({
    "str", "int", "float", "bool", "bytes", "dict", "list", "set", "tuple",
    "frozenset", "Path", "Any", "None",
})

# Everything that runs on the user's machine as part of a hook or an install,
# where a load failure costs the session. No exceptions permitted here.
REQUIRED_CLEAN = [
    "clean-rag/hooks",
    "clean-rag/server/graph_store.py",
    "clean-rag/server/file_scan.py",
    "clean-rag/cli/clone-reference.py",
    "scripts/setup.py",
]

# Files known to still carry a bare union, none of them reachable from a hook.
# This list is a ratchet: a file may leave it, and nothing may join it. Kept so
# the remaining debt stays visible instead of silently passing an easier test.
KNOWN_UNFIXED = frozenset({
    "clean-rag/install.py",
    "clean-rag/server/app.py",
    "clean-rag/server/auto_reindex.py",
    "clean-rag/server/code_chunker.py",
    "clean-rag/server/docs_fetch.py",
    "clean-rag/server/edge_extraction.py",
    "clean-rag/server/indexing.py",
    "clean-rag/server/kanban.py",
    "clean-rag/server/metrics.py",
    "clean-rag/server/resource_guard.py",
    "clean-rag/server/search.py",
    "clean-rag/server/store.py",
    "clean-rag/tests/test_badcop_round5_complete_project_sources.py",
    "clean-rag/tests/test_incomplete_index_web_fallback_interaction.py",
    "clean-rag/tests/test_mixed_source_over_suppression.py",
    "scripts/changes_core.py",
    "scripts/clone-docs.py",
    "scripts/download_csharp_github.py",
    "scripts/fetch-docs.py",
    "scripts/install-terminal-mode-reset.py",
    "scripts/memory-watcher.py",
})


def _is_type_union(node: ast.AST) -> bool:
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)):
        return False
    for side in (node.left, node.right):
        base = side
        while isinstance(base, ast.Subscript):
            base = base.value
        if isinstance(base, ast.Name) and base.id in TYPE_NAMES:
            return True
        if isinstance(base, ast.Constant) and base.value is None:
            return True
        if isinstance(base, ast.Attribute) and base.attr in TYPE_NAMES:
            return True
    return False


def _annotations_of(tree: ast.Module) -> list[ast.expr]:
    out: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            args = list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)
            args += [a.vararg, a.kwarg]
            out += [x.annotation for x in args if x is not None and x.annotation]
            if node.returns is not None:
                out.append(node.returns)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            out.append(node.annotation)
    return out


def unsafe_union_lines(path: Path) -> list[int]:
    """Lines whose annotation would raise on the floor, [] if the file is safe.

    A file carrying `from __future__ import annotations` is safe whatever its
    annotations say, because they are never evaluated.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    if any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
           and any(alias.name == "annotations" for alias in n.names)
           for n in tree.body):
        return []
    hits: set[int] = set()
    for annotation in _annotations_of(tree):
        for sub in ast.walk(annotation):
            if _is_type_union(sub):
                hits.add(sub.lineno)
    return sorted(hits)


def _required_files() -> list[Path]:
    files: list[Path] = []
    for entry in REQUIRED_CLEAN:
        target = REPO / entry
        files.extend(sorted(target.glob("*.py")) if target.is_dir() else [target])
    return files


@pytest.mark.parametrize(
    "path", _required_files(), ids=lambda p: p.relative_to(REPO).as_posix()
)
def test_hook_surface_has_no_runtime_only_annotation(path: Path) -> None:
    lines = unsafe_union_lines(path)
    assert not lines, (
        f"{path.relative_to(REPO).as_posix()} uses a bare `X | Y` annotation at "
        f"line(s) {lines}. That is evaluated at import time and raises TypeError "
        f"on Python {FLOOR[0]}.{FLOOR[1]}, above the module's own fail open "
        f"handler. Add `from __future__ import annotations` below the docstring."
    )


def test_known_unfixed_list_only_shrinks() -> None:
    """Nothing outside the ratchet may start failing, and the ratchet may shrink.

    Asserting only one direction is deliberate. A file that gets fixed should
    not turn this red and force an unrelated edit, but a new offender should.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "*.py"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if listing.returncode != 0:
        pytest.skip("git ls-files unavailable, cannot enumerate tracked files")

    offenders = set()
    for rel in listing.stdout.split():
        path = REPO / rel
        if not path.exists():  # staged deletion
            continue
        try:
            if unsafe_union_lines(path):
                offenders.add(rel)
        except (SyntaxError, UnicodeDecodeError):
            continue

    new = sorted(offenders - KNOWN_UNFIXED)
    assert not new, (
        "These files newly use a bare `X | Y` annotation with no "
        f"`from __future__ import annotations`, so they cannot import on Python "
        f"{FLOOR[0]}.{FLOOR[1]}: {new}"
    )
