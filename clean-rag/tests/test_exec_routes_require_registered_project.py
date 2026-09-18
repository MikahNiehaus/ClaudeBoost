"""Routes that run a project's own tooling must not run it from anywhere.

/run-tests, /mutation-test and /security-scan all take ``project_path`` from
the request body and then execute the tooling that path supplies: ``npm test``
runs whatever ``scripts.test`` says, ``npx vitest`` runs whatever sits in that
project's node_modules, ``pytest`` imports that project's conftest.py. There is
no way to run a project's tests without executing its code, so the boundary has
to be on which paths are allowed to supply a command, not on the command.

state/projects.json is the operator's own allowlist, and it means "this server
indexed this directory" only while indexing is the one thing that writes it. A
/register-project route used to write an entry straight from a request body, so
one POST registered any path and the next ran its tests; TestOnlyIndexingCanRegisterAProject
below is what keeps that shape from coming back.

/index-project is deliberately not gated the same way. Registering a path that
is not yet registered is the whole point of it, and it never executes anything
from the tree.

Every test here works inside tmp_path, and the empty_registry fixture repoints
every loaded module that holds a real STATE_DIR or DATABASES_DIR, not only the
one whose handler is under test. Patching app.py alone was not enough and is
the trap that fixture's docstring describes.
"""
import ast
import asyncio
import functools
import inspect
import json
import sys
import textwrap
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app as app_mod  # noqa: E402
from server import config as config_mod  # noqa: E402


class _StubRequest:
    """Enough of aiohttp's Request for the handlers under test.

    A JSON body, plus the query string and method /graphrag-status reads before
    it falls back to the body.
    """

    def __init__(self, body, query=None, method="POST"):
        self._body = body
        self.query = query or {}
        self.method = method

    async def json(self):
        return self._body


def _attacker_project(root: Path) -> Path:
    """A directory whose package.json test script writes a file when it runs.

    The proof is the side effect, not the response: if PWNED.txt appears, the
    server executed a command that arrived with the request.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "payload.js").write_text(
        "require('fs').writeFileSync('PWNED.txt', 'executed');\n", encoding="utf-8",
    )
    (root / "package.json").write_text(
        json.dumps({
            "name": "attacker-controlled",
            "version": "1.0.0",
            "scripts": {"test": "node payload.js"},
        }),
        encoding="utf-8",
    )
    return root


#: Config constants that resolve to a real directory on the operator's machine.
#: STATE_DIR holds projects.json, DATABASES_DIR holds every project's chroma
#: index, graph.db and manifest.json.
#:
#: CLEAN_RAG_HOME, their parent, is deliberately not here, and a test that
#: needs it isolated has to solve that rather than assume this fixture did.
#: It is not only a data root: graphrag_client resolves the graph service
#: script and its venv python underneath it, and config derives the two names
#: above from it. Rebasing it onto a scratch directory would move the server's
#: own source out from under the code that reads it, which breaks the run
#: instead of isolating it.
_REAL_TREE_NAMES = ("STATE_DIR", "DATABASES_DIR")

#: Captured at import, before any fixture runs. config is itself one of the
#: modules that gets repointed, so reading the real value back off it after
#: patching would compare the scratch tree against itself and call every
#: correctly isolated module a straggler.
_REAL_TREES = {name: getattr(config_mod, name) for name in _REAL_TREE_NAMES}


def _containing_real_tree(value):
    """Which real tree this path sits in, or None."""
    for name, root in _REAL_TREES.items():
        try:
            if value == root or value.is_relative_to(root):
                return name
        except (OSError, ValueError):
            continue
    return None


def _real_tree_bindings():
    """(module, attribute, value, tree) for every path into a real directory.

    Two layers, and missing the second is what made an earlier version of this
    fixture look isolated while it was not.

    The first layer is the constants themselves. Eight modules in this package
    do their own ``from .config import STATE_DIR``, and that form copies the
    binding rather than aliasing the module: it creates a new name pointing at
    the object, so rebinding one module's name leaves every other one pointing
    at the original. That is what unittest.mock's "Where to patch" means by
    patching the name used by the system under test, and monkeypatch.setattr
    has the same semantics. Patching app.py alone therefore isolated nothing
    past the first call, because _update_project_registry reads
    indexing.STATE_DIR.

    The second layer is everything computed from those constants at import.
    ``indexing._INDEX_LOCK_PATH = STATE_DIR / "index-lock.json"`` is evaluated
    once, at import, into its own constant, so repointing STATE_DIR afterwards
    does not move it. Three of these exist right now: that lock,
    app._HEARTBEAT_PATH and app._SEARCH_LOG_PATH. A test taking the index lock
    was creating and deleting a real file in the operator's state directory,
    and contending with the running server for it.

    Scanning for any Path that resolves inside a real tree covers both layers
    and the next constant derived from either, which naming them would not.
    """
    package = app_mod.__name__.split(".")[0]
    for module_name, module in list(sys.modules.items()):
        if module_name.split(".")[0] != package:
            continue
        for attr, value in list(vars(module).items()):
            if attr.startswith("__") or not isinstance(value, Path):
                continue
            tree = _containing_real_tree(value)
            if tree is not None:
                yield module, attr, value, tree


def _assert_isolated() -> None:
    """Nothing loaded may still resolve into a real tree."""
    stragglers = [
        f"{module.__name__}.{attr} = {value}"
        for module, attr, value, _ in _real_tree_bindings()
    ]
    assert not stragglers, (
        f"these still resolve inside the operator's own directories, so "
        f"anything reached through them writes real state: {stragglers}"
    )


@pytest.fixture
def empty_registry(tmp_path, monkeypatch):
    """Repoint every path into a real tree at a scratch one.

    Returns the scratch state directory, which is where projects.json lands.
    Paths below a tree keep their relative position, so index-lock.json is
    still called index-lock.json and still sits beside the registry.

    Deliberately not backstopped by the real registry's mtime, which looks like
    the stronger check. The server on 8613 rewrites that file on its own sweep,
    so its mtime cannot distinguish a test writing it from the server writing
    it. The binding scan is deterministic and fails earlier.
    """
    scratch = {}
    for name in _REAL_TREE_NAMES:
        target = tmp_path / name.split("_")[0].lower()
        target.mkdir(exist_ok=True)
        scratch[name] = target

    for module, attr, value, tree in list(_real_tree_bindings()):
        root = _REAL_TREES[tree]
        rebased = (
            scratch[tree] if value == root else scratch[tree] / value.relative_to(root)
        )
        monkeypatch.setattr(module, attr, rebased)

    _assert_isolated()
    return scratch["STATE_DIR"]


def _register(state: Path, project_path: Path) -> None:
    (state / "projects.json").write_text(
        json.dumps({"proj": {"project_path": str(project_path), "source": "clean-rag"}}),
        encoding="utf-8",
    )


#: The registry filename, as the code that touches it spells it.
_REGISTRY_FILENAME = "projects.json"

#: Calls that put bytes on disk. json.dump and Path.write_text are what the
#: package uses; the rest are here so a writer that reaches for a different one
#: is still recognised as a writer.
_WRITE_CALLS = frozenset({
    "write_text", "write_bytes", "write_json", "dump", "replace", "rename",
})


def _source_ast(func):
    """The AST of one function, or None when its source cannot be read."""
    try:
        return ast.parse(textwrap.dedent(inspect.getsource(func)))
    except (OSError, TypeError, SyntaxError, IndentationError):
        return None


def _called_name(node) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    return getattr(node.func, "id", None) or getattr(node.func, "attr", None)


def _opens_for_writing(node) -> bool:
    """``open(path, "w")`` and friends, which name no write method of their own."""
    if _called_name(node) != "open":
        return False
    modes = [a.value for a in node.args
             if isinstance(a, ast.Constant) and isinstance(a.value, str)]
    modes += [k.value.value for k in node.keywords
              if k.arg == "mode" and isinstance(k.value, ast.Constant)]
    return any(set("wa+") & set(m) for m in modes)


def _writes_the_registry(tree) -> bool:
    """Does this function name the registry file and then write something?

    Both halves are required so the readers stay clear of it: _list_projects
    (app.py) and _load_registry (reindex_unit.py) name the same file and only
    ever call read_text.
    """
    nodes = list(ast.walk(tree))
    names_it = any(
        isinstance(n, ast.Constant) and n.value == _REGISTRY_FILENAME for n in nodes
    )
    if not names_it:
        return False
    return any(
        _called_name(n) in _WRITE_CALLS or _opens_for_writing(n) for n in nodes
    )


#: How far out the walk follows a callee: anything whose source file is inside
#: the clean-rag checkout. The rule used to be "same top level package as
#: server.app", and that stopped the walk dead at the package boundary. A
#: handler calling a helper one directory over in tests/ or hooks/ was reported
#: as reaching nothing even when the call was a plain name, which made the
#: package filter a wider hole than any of the indirection below. Outside the
#: checkout (aiohttp, the stdlib, site-packages) is still not followed, which is
#: what keeps the walk bounded.
_CHECKOUT_ROOT = Path(app_mod.__file__).resolve().parents[1]


def _inside_checkout(obj) -> bool:
    try:
        return Path(inspect.getfile(obj)).resolve().is_relative_to(_CHECKOUT_ROOT)
    except (TypeError, OSError, ValueError):
        return False


def _globals_of(func):
    """The namespace a call target resolves its own names in.

    A function carries __globals__. A class does not, and aiohttp registers a
    class based view as the handler itself, so fall back to the module it was
    defined in, which is the namespace Python would use anyway.
    """
    globs = getattr(func, "__globals__", None)
    if globs is not None:
        return globs
    module = sys.modules.get(getattr(func, "__module__", ""))
    return vars(module) if module is not None else {}


def _enclosing_class(func):
    """The class a method is defined in, resolved from its qualname.

    This is what lets ``self.mint()`` resolve. ``self`` is a local and never a
    global, so a class based view's calls to its own methods are invisible
    without it.
    """
    parts = getattr(func, "__qualname__", "").split(".")[:-1]
    if not parts:
        return None
    obj = _globals_of(func).get(parts[0])
    for part in parts[1:]:
        obj = getattr(obj, part, None)
    return obj if inspect.isclass(obj) else None


def _functions_behind(candidate, _nested=False):
    """Every function a resolved object stands for.

    A call target is not always a plain function, and each of these shapes is
    something an ordinary aiohttp app does:

    - a bound method, from a module level instance or from ``self``;
    - a class, because add_view registers the view class as the handler;
    - a container of handlers, which is what a command dispatch table is;
    - a functools.partial around any of the above.

    One level of container nesting only. A table of tables is not a shape this
    codebase has, and unbounded recursion over arbitrary globals is not worth
    the reach.
    """
    if isinstance(candidate, functools.partial):
        candidate = candidate.func
    if inspect.ismethod(candidate):
        candidate = candidate.__func__
    if not _nested and isinstance(candidate, (dict, list, tuple, set, frozenset)):
        values = candidate.values() if isinstance(candidate, dict) else candidate
        return [f for v in values for f in _functions_behind(v, _nested=True)]
    if not _inside_checkout(candidate):
        return []
    if inspect.isfunction(candidate):
        return [candidate]
    if inspect.isclass(candidate):
        # Inherited members are filtered too, or every class based view drags
        # aiohttp's own View methods into the walk.
        return [
            f for _, f in inspect.getmembers(candidate, inspect.isfunction)
            if _inside_checkout(f)
        ]
    return []


def _reachable_callees(func, tree):
    """Functions inside the checkout that ``func`` references by name.

    References, not calls: handle_index_project passes index_project to
    functools.partial rather than calling it, and a handler that hands the
    writer to an executor is reaching it just as surely as one that calls it.
    Resolution goes through the function's own globals, which is the same
    namespace Python itself uses at call time.
    """
    if inspect.isclass(func):
        yield from _functions_behind(func)
    globs = _globals_of(func)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            candidate = globs.get(node.id)
        elif isinstance(node, ast.Attribute):
            base_name = getattr(node.value, "id", None)
            if base_name in ("self", "cls"):
                base = _enclosing_class(func)
            else:
                base = globs.get(base_name)
            candidate = getattr(base, node.attr, None) if base is not None else None
        else:
            continue
        yield from _functions_behind(candidate)


def _write_chain(func, seen=None, prefix=()):
    """The call chain from ``func`` to a registry writer, or None."""
    seen = set() if seen is None else seen
    key = f"{getattr(func, '__module__', '?')}.{getattr(func, '__qualname__', func)}"
    if key in seen:
        return None
    seen.add(key)
    tree = _source_ast(func)
    if tree is None:
        return None
    here = (*prefix, key)
    if _writes_the_registry(tree):
        return here
    for callee in _reachable_callees(func, tree):
        found = _write_chain(callee, seen, here)
        if found:
            return found
    return None


def _routes_reaching_a_registry_writer(app) -> dict:
    """Served route path -> the call chain by which it reaches the writer.

    Handlers come from the built app's own router, the same way
    tests/test_skill_rag_routes.py reads it: a list mirrored into a test file
    rots and stops catching anything. The app is built but never started, so
    the on_startup model warmup does not run.
    """
    reaching = {}
    for route in app.router.routes():
        canonical = getattr(route.resource, "canonical", None)
        if not canonical:
            continue
        chain = _write_chain(route.handler)
        if chain:
            reaching[canonical] = chain
    return reaching


#: The one function allowed to write the registry.
_REGISTRY_WRITER = "_update_project_registry"

#: Writers that may only ever REMOVE entries, with the route that reaches each.
#:
#: The property this whole class defends is that registry membership means the
#: server indexed the directory, because membership is the allowlist the exec
#: routes check. Only ADDING an entry can break that. A function that can just
#: delete one cannot mint the allowlist entry an attacker needs, so it does not
#: reopen the hole.
#:
#: That distinction already existed here as a sentence, in
#: test_the_registry_has_exactly_one_writer_in_the_server_package's docstring,
#: excusing fix_boat_bug.py on exactly this ground. It was never checked. When
#: /delete-project made the same argument from inside the server package and a
#: route, the sentence was all there was to appeal to. So it is a rule now:
#: every name here has to pass test_a_removal_only_writer_really_cannot_add,
#: which reads its source and fails if it can put an entry in.
#:
#: Adding a name here is not a formality. It widens what may touch the file
#: that gates code execution.
_REMOVAL_ONLY_WRITERS = {
    "indexing.py:_remove_from_project_registry": "/delete-project",
}


#: Ways a function puts an entry INTO a mapping. `registry[pid] = entry` is the
#: shape _update_project_registry uses; the other two are how the same thing is
#: written without a subscript assignment.
def _can_add_a_registry_entry(tree) -> bool:
    """Whether this function can put an entry into the registry mapping.

    Deliberately shape based rather than name based: the question is what the
    code can do, not what it is called. A remover deletes keys and rewrites the
    file with fewer of them, and never assigns into the mapping.

    Over approximates on purpose. Any subscript store, `update` or `setdefault`
    anywhere in the function counts, even against an unrelated dict. That
    direction costs a loud failure on a false positive and never a silent pass
    on a real one, which is the same trade the route walk above documents.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Subscript):
                    return True
        if _called_name(node) in {"update", "setdefault"}:
            return True
    return False

#: The only places in the server package allowed to name it: its own
#: definition, and the indexing pipeline that calls it.
_ALLOWED_WRITER_REFERENCE_SITES = {
    "indexing.py:_update_project_registry",
    "indexing.py:index_project",
}


def _writer_references(node, enclosing: str):
    """Yield the enclosing name of every mention of the writer under ``node``."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if child.name == _REGISTRY_WRITER:
                yield child.name
            yield from _writer_references(child, child.name)
            continue
        named = (
            (isinstance(child, ast.Name) and child.id == _REGISTRY_WRITER)
            or (isinstance(child, ast.Attribute) and child.attr == _REGISTRY_WRITER)
            # A literal string is how getattr reaches a function without ever
            # writing its name as an expression, so it counts as naming it.
            or (isinstance(child, ast.Constant) and child.value == _REGISTRY_WRITER)
        )
        if named:
            yield enclosing
        yield from _writer_references(child, enclosing)


def _writer_reference_sites() -> set[str]:
    """``file.py:enclosing`` for everything in the package that names the writer.

    The second check on the same property, and deliberately not a refinement of
    the route walk: it starts from the writer's name rather than from a handler,
    reads source rather than resolving objects, and so it is not fooled by the
    thing that fools a reachability walk. A dispatch table holding the writer,
    a partial around it, a class attribute set to it, or a getattr with its name
    spelled out all put the identifier in some module here, whoever ends up
    calling it. Both checks now have to be defeated at once, which takes
    building the writer's name at runtime out of pieces.

    Module level references report as ``file.py:<module>``, which is the shape
    a dispatch table defined at import time has.
    """
    package_dir = Path(app_mod.__file__).parent
    sites = set()
    for source in sorted(package_dir.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for enclosing in _writer_references(tree, "<module>"):
            sites.add(f"{source.name}:{enclosing}")
    return sites


def _registry_writers_in_package() -> list[str]:
    """``file.py:function`` for every function in the package that writes it."""
    package_dir = Path(app_mod.__file__).parent
    writers = []
    for source in sorted(package_dir.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _writes_the_registry(node):
                    writers.append(f"{source.name}:{node.name}")
    return writers


class TestRunTests:
    def test_unregistered_path_is_refused_and_nothing_runs(self, tmp_path, empty_registry):
        project = _attacker_project(tmp_path / "attacker")

        response = asyncio.run(
            app_mod.handle_run_tests(_StubRequest({"project_path": str(project)}))
        )

        assert response.status == 403, (
            "an unregistered project_path was accepted, so a request body value "
            "alone decides which directory's code the server runs"
        )
        assert not (project / "PWNED.txt").exists(), (
            "the project's own test script ran: the request body chose the "
            "command and the server executed it"
        )

    def test_a_registered_path_still_runs(self, tmp_path, empty_registry):
        """The gate must not break the legitimate caller.

        clean-rag/hooks/auto-test-gate.py posts the session's git root here on
        every Stop, and that has to keep working for a project the operator
        indexed.
        """
        project = tmp_path / "real"
        project.mkdir()
        (project / "test_math.py").write_text(
            "def test_adds():\n    assert 1 + 1 == 2\n", encoding="utf-8",
        )
        _register(empty_registry, project)

        response = asyncio.run(
            app_mod.handle_run_tests(_StubRequest({"project_path": str(project)}))
        )

        assert response.status == 200
        body = json.loads(response.body.decode("utf-8"))
        assert body["has_tests"] is True
        assert body["passed"] is True, body

    def test_traversal_out_of_a_registered_root_is_refused(self, tmp_path, empty_registry):
        """The comparison is on the resolved path, so a registered prefix plus
        ``..`` cannot walk out of it."""
        registered = tmp_path / "real"
        registered.mkdir()
        _register(empty_registry, registered)
        outside = _attacker_project(tmp_path / "attacker")

        escaped = registered / ".." / "attacker"
        response = asyncio.run(
            app_mod.handle_run_tests(_StubRequest({"project_path": str(escaped)}))
        )

        assert response.status == 403
        assert not (outside / "PWNED.txt").exists()

    def test_a_subdirectory_of_a_registered_project_is_refused(self, tmp_path, empty_registry):
        """Registering a project must not also authorise everything under it.

        node_modules lives under a registered root in every project with a
        lockfile, and its contents are not the operator's choice.
        """
        registered = tmp_path / "real"
        registered.mkdir()
        _register(empty_registry, registered)
        nested = _attacker_project(registered / "node_modules" / "evil")

        response = asyncio.run(
            app_mod.handle_run_tests(_StubRequest({"project_path": str(nested)}))
        )

        assert response.status == 403
        assert not (nested / "PWNED.txt").exists()


class TestOtherExecutingRoutes:
    @pytest.mark.parametrize(
        "handler_name", ["handle_mutation_test", "handle_security_scan"],
    )
    def test_unregistered_path_is_refused(self, tmp_path, empty_registry, handler_name):
        project = _attacker_project(tmp_path / "attacker")
        handler = getattr(app_mod, handler_name)

        response = asyncio.run(
            handler(_StubRequest({"project_path": str(project), "changed_files": []}))
        )

        assert response.status == 403, f"{handler_name} accepted an unregistered path"


class TestGraphragRoutesRequireARegisteredProject:
    """These two read rather than run, and still take the gate.

    /graphrag-build hands project_path to the graph service, which walks the
    directory and ingests the contents of every file scan_project accepts;
    /graphrag-query hands those contents back as an answer. Nothing from the
    tree is executed (graphrag_client spawns the server's own interpreter on
    the server's own script, with the path as data), so this is an arbitrary
    directory read with a readback channel rather than code execution. An
    ungated pair means one request body points the reader at a home directory
    and the next asks it what it found.

    The proxy is stubbed in every case here. Calling the real one starts the
    graph service in its own console and begins an hours long build, which is
    not something a test suite may do to the machine it runs on.
    """

    @pytest.fixture
    def calls(self, monkeypatch):
        seen = []

        def _stub(*args):
            seen.append(args)
            return {"started": True}

        for name in ("graphrag_build", "graphrag_query", "graphrag_status"):
            monkeypatch.setattr(app_mod, name, _stub)
        return seen

    def test_an_unregistered_path_is_refused_before_the_service_is_touched(
        self, tmp_path, empty_registry, calls,
    ):
        project = tmp_path / "somebody-elses-checkout"
        project.mkdir()

        response = asyncio.run(
            app_mod.handle_graphrag_build(_StubRequest({"project_path": str(project)}))
        )

        assert response.status == 403
        assert calls == [], "the graph service was asked to read a refused path"

    def test_the_query_side_is_refused_too(self, tmp_path, empty_registry, calls):
        """Gating only the build would leave a graph built before the gate, or
        by another route, readable by anyone who can reach the port."""
        project = tmp_path / "somebody-elses-checkout"
        project.mkdir()

        response = asyncio.run(
            app_mod.handle_graphrag_query(
                _StubRequest({"project_path": str(project), "query": "what is here"})
            )
        )

        assert response.status == 403
        assert calls == []

    def test_the_refusal_says_what_this_route_actually_does(
        self, tmp_path, empty_registry, calls,
    ):
        """A caller refused here is not running tests, and being told it was
        sends them looking for the wrong thing."""
        project = tmp_path / "somebody-elses-checkout"
        project.mkdir()

        response = asyncio.run(
            app_mod.handle_graphrag_build(_StubRequest({"project_path": str(project)}))
        )
        message = json.loads(response.body.decode("utf-8"))["error"]

        assert "reads every source file" in message
        assert "test tooling" not in message

    def test_a_registered_path_still_builds(self, tmp_path, empty_registry, calls):
        """The gate must not break the operator's own project. Indexing is what
        registers a path, and it is a different route, so nothing is circular."""
        project = tmp_path / "mine"
        project.mkdir()
        _register(empty_registry, project)

        response = asyncio.run(
            app_mod.handle_graphrag_build(_StubRequest({"project_path": str(project)}))
        )

        assert response.status == 200
        assert calls == [(str(project),)]

    def test_status_is_not_gated(self, tmp_path, empty_registry, calls):
        """Reading build progress touches only clean-rag's own progress.json,
        never the project directory, so refusing it would cost the caller the
        cheap way to learn a build is not there and protect nothing."""
        project = tmp_path / "unregistered"
        project.mkdir()

        response = asyncio.run(
            app_mod.handle_graphrag_status(_StubRequest({"project_path": str(project)}))
        )

        assert response.status == 200


class _OfflineEmbedder:
    """Stand in for the ModelCache that handle_index_project checks for.

    Two things need it. The handler answers 503 when _model_cache is None, and
    index_project takes its backward compatible branch for anything that is not
    a real ModelCache, so a plain object with embed() runs the whole indexing
    path without loading a model or touching the network.
    """

    model_name = "offline-test-embedder"

    def embed(self, texts):
        return [[0.0] * 8 for _ in texts]


class TestIndexProjectIsNotGated:
    def test_registering_a_brand_new_path_is_still_possible(self, tmp_path, empty_registry):
        """The allowlist must not be circular.

        /index-project is how a path gets into the registry, so requiring it to
        already be there would make a first time index impossible. It also runs
        nothing from the tree, so it does not need the gate.
        """
        assert app_mod._registered_project_or_error(
            str(tmp_path), app_mod._RUNS_PROJECT_TOOLING,
        ) is not None, "test setup: this path must not be registered"
        source = Path(app_mod.handle_index_project.__code__.co_filename).read_text(
            encoding="utf-8",
        )
        index_body = source.split("async def handle_index_project", 1)[1].split(
            "\nasync def ", 1,
        )[0]
        assert "_registered_project_or_error" not in index_body, (
            "handle_index_project must not require the path to be registered "
            "already, or a first time index can never happen"
        )

    def test_indexing_writes_the_registry_only_inside_the_scratch_tree(
        self, tmp_path, empty_registry, monkeypatch,
    ):
        """Exercises the fixture's isolation instead of asserting it.

        This is the case that would have written the operator's own registry
        before: it is the first test here to reach _update_project_registry,
        which reads indexing.STATE_DIR rather than app.STATE_DIR. It passed
        under the old fixture too, and silently, because nothing looked at
        where the write landed. Both halves are checked now: the entry is in
        the scratch registry, and this path is absent from the real one.
        """
        monkeypatch.setattr(app_mod, "_model_cache", _OfflineEmbedder())
        project = tmp_path / "indexable"
        project.mkdir()
        (project / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n", encoding="utf-8",
        )

        response = asyncio.run(
            app_mod.handle_index_project(_StubRequest({"project_path": str(project)}))
        )
        assert response.status == 200, response.body

        scratch_registry = empty_registry / "projects.json"
        assert scratch_registry.exists(), "indexing wrote no registry at all"
        indexed = {
            str(Path(entry["project_path"]).resolve())
            for entry in json.loads(
                scratch_registry.read_text(encoding="utf-8")
            ).values()
        }
        assert str(project.resolve()) in indexed

        real_registry = _REAL_TREES["STATE_DIR"] / "projects.json"
        real_text = (
            real_registry.read_text(encoding="utf-8") if real_registry.exists() else ""
        )
        assert str(project.resolve()) not in real_text, (
            f"indexing a scratch project wrote into {real_registry}, so this "
            f"suite is editing the operator's own project registry"
        )


class TestBrowserOriginsAreRefused:
    """A loopback bind is not a boundary by itself, and these routes run code.

    Same defect and same fix as the Model Context Protocol TypeScript SDK
    advisory GHSA-w48q-cv73-mx4w: validate Host so a rebound DNS name is
    refused, and refuse a cross origin browser request outright.
    """

    @staticmethod
    def _client():
        async def ok(request):
            return web.json_response({"ok": True})

        app = web.Application(
            middlewares=[app_mod.local_origin_middleware, app_mod.error_middleware],
        )
        app.router.add_post("/run-tests", ok)
        return TestClient(TestServer(app))

    def _post(self, headers):
        async def run():
            client = self._client()
            await client.start_server()
            try:
                resp = await client.post("/run-tests", json={}, headers=headers)
                return resp.status
            finally:
                await client.close()

        return asyncio.run(run())

    def test_a_local_tool_with_no_origin_is_allowed(self):
        assert self._post({}) == 200

    def test_a_cross_origin_browser_request_is_refused(self):
        assert self._post({"Origin": "https://evil.example"}) == 403

    def test_a_loopback_origin_is_allowed(self):
        assert self._post({"Origin": "http://127.0.0.1:8613"}) == 200

    def test_a_rebound_dns_name_in_host_is_refused(self):
        assert self._post({"Host": "evil.example:8613"}) == 403

    def test_a_lookalike_loopback_host_is_refused(self):
        """``127.0.0.1.evil.example`` resolves to the attacker, and a substring
        or prefix check would accept it."""
        assert self._post({"Host": "127.0.0.1.evil.example:8613"}) == 403


def _mint_registry_entry(body: dict) -> None:
    """Add a registry entry from a request body: the shape the gate must never
    let a route reach. Reads, adds, writes back, as the real writer does."""
    registry = app_mod._list_projects()
    registry["indirect_mint"] = {
        "project_path": body["project_path"], "source": "external",
    }
    registry_path = app_mod.STATE_DIR / "projects.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")


#: A command dispatch table, the "router of routers" shape. The call target is
#: an ast.Subscript, which is not a name the walk can resolve on its own.
_MINT_ACTIONS = {"mint": _mint_registry_entry}


async def _dispatch_table_handler(request):
    action = _MINT_ACTIONS["mint"]
    action(await request.json())
    return web.json_response({"registered": "indirect_mint"})


class _RegistryWritingView:
    """A class based view, whose calls to its own helpers go through ``self``.

    ``self`` is a local and never a global, so resolving this needs the class
    behind the method rather than the module namespace.
    """

    async def post(self, request):
        await self._mint(request)
        return web.json_response({"registered": "indirect_mint"})

    async def _mint(self, request):
        _mint_registry_entry(await request.json())


_bound_method_handler = _RegistryWritingView().post


async def _direct_call_handler(request):
    """No indirection at all. This one is here because the walk missed it too:
    the callee is defined outside the server package."""
    _mint_registry_entry(await request.json())
    return web.json_response({"registered": "indirect_mint"})


class TestOnlyIndexingCanRegisterAProject:
    """The allowlist above is only worth checking while nothing mints entries.

    /register-project used to write state/projects.json straight from a request
    body: no auth, no check the directory existed, no index behind it. One POST
    put any path in the registry and the next POST ran its package.json test
    script, so the gate refused nothing a caller could not undo in the call
    before. It was reachable from the one place that matters here, too:
    clean-rag/hooks/research-agent-bash-guard.py cages that agent's Bash to
    curl against this server, and the agent reads untrusted web pages.

    What is left is indexing, which requires the directory to exist and walks
    and embeds it. So a path is in the registry because this server indexed it,
    which is the provenance the gate claims.
    """

    def test_only_the_indexing_route_reaches_a_registry_writer(self):
        """Ask who can reach the writer, not what any route is called.

        This replaces an assertion that "/register-project" was absent from the
        route table. That assertion was inert: it pinned the name of one
        deleted route, so the identical hole reopened under any other name
        passed it. Proven, not assumed, by adding a route that writes
        projects.json from a request body under the name "/reregister-project"
        and watching the old assertion stay green.

        A name cannot be the subject here, because the property is about
        behaviour: no route may put an entry in the registry except by
        indexing. So this walks out from the handlers the dispatcher actually
        serves, through the call graph, and asks which of them can arrive at
        code that writes the file. /index-project is the one allowed answer and
        it has to be there, since registering a path is its whole purpose and a
        circular allowlist could never take a first entry.

        What it cannot see, stated so the next reader does not over trust it,
        and every item measured rather than guessed.

        A callee reached by ``getattr`` with a name computed at runtime, or by
        exec, eval or an import done inside the function. This is the same
        limit PyCG states for itself ("the effects of functions such as getattr
        and setattr are ignored", arXiv 2103.00587 section IV), and it is not a
        gap a better walk closes: resolving it means running the program.

        A handler whose source is unavailable, and a callee whose source file
        is outside the clean-rag checkout, which is now the boundary rather
        than the server package. Both are refusals to guess, not oversights,
        but a writer smuggled in through a site-packages helper is invisible
        here and only the reference check below would see it.

        A handler that never names projects.json in its own body because it
        closed over a path built somewhere else: an early draft of the bites
        check in test_index_then_run_tests_registry_escalation.py did exactly
        that and slipped through.

        Dispatch tables, bound methods and class based views WERE on this list
        and are not any more; the three tests below build each shape against a
        real app and require the walk to see it. Following a dispatch table
        over approximates, since every function in the table counts as reached
        whether or not that key is ever dispatched. That direction is the safe
        one here: it costs a loud failure, never a silent pass.
        """
        reaching = {
            path: chain
            for path, chain in _routes_reaching_a_registry_writer(
                app_mod.create_app()
            ).items()
        }

        allowed = {"/index-project", *_REMOVAL_ONLY_WRITERS.values()}
        assert set(reaching) == allowed, (
            "a route other than /index-project can reach the code that writes "
            "state/projects.json, which makes the allowlist self service: the "
            f"caller registers its own directory and then runs its tests. "
            f"Reachable from: { {p: ' -> '.join(c) for p, c in reaching.items()} }"
        )

        # A removal only route is excused from the rule above, so the chain it
        # actually takes has to end at the remover it was excused for. Without
        # this, /delete-project growing a call to the adding writer would be
        # covered by its own exemption.
        for path, route in ((v, v) for v in _REMOVAL_ONLY_WRITERS.values()):
            if route not in reaching:
                continue
            terminal = reaching[route][-1].rsplit(".", 1)[-1]
            expected = {
                site.split(":", 1)[1]
                for site, r in _REMOVAL_ONLY_WRITERS.items() if r == route
            }
            assert terminal in expected, (
                f"{route} is exempt because it only removes entries, but its "
                f"call chain ends at {terminal!r}, not at {sorted(expected)}. "
                f"Chain: {' -> '.join(reaching[route])}"
            )

    @pytest.mark.parametrize(
        "route, handler",
        [
            ("/dispatch-mint", _dispatch_table_handler),
            ("/method-mint", _bound_method_handler),
            ("/direct-mint", _direct_call_handler),
        ],
    )
    def test_the_walk_sees_a_writer_reached_indirectly(
        self, empty_registry, tmp_path, route, handler,
    ):
        """Three spellings of the same reach, all of which the walk once missed.

        Each adds a route to a real app, asks the walk about it, and then calls
        the handler for real and reads the scratch registry back. The write
        landing is what makes this a test of the walk rather than of a mock: if
        the walk reported nothing and the entry is on disk anyway, the check
        that guards the allowlist is decorative.

        The direct call case is the one that shows the old failure was not only
        about indirection. Its handler calls the writer with a plain name, no
        table and no method, and the walk still missed it, because the callee
        is defined outside the server package and the old filter refused to
        follow anything outside it.
        """
        app = app_mod.create_app()
        app.router.add_post(route, handler)

        reaching = _routes_reaching_a_registry_writer(app)

        assert route in reaching, (
            f"{route} reaches the registry writer and the walk did not see it, "
            f"so a route that mints its own registry entry ships green. "
            f"Reachable from: { {p: ' -> '.join(c) for p, c in reaching.items()} }"
        )

        asyncio.run(handler(_StubRequest({"project_path": str(tmp_path / "any")})))
        written = json.loads(
            (empty_registry / "projects.json").read_text(encoding="utf-8")
        )
        assert "indirect_mint" in written, (
            "test setup: the handler was supposed to write a real entry, so "
            "the walk had something real to miss"
        )

    def test_nothing_outside_the_indexing_pipeline_names_the_writer(self):
        """The independent second check, which a reachability walk cannot be.

        The walk resolves objects and can be fooled by any spelling it cannot
        resolve. This reads source and asks the opposite question: who in this
        package writes the identifier at all. A dispatch table holding the
        writer, a partial around it, a class attribute assigned to it, or a
        getattr with the name spelled out are all invisible to one check and
        obvious to the other, so a new way in has to defeat both at once.
        """
        sites = _writer_reference_sites()

        assert sites == _ALLOWED_WRITER_REFERENCE_SITES, (
            f"something other than the indexing pipeline names "
            f"{_REGISTRY_WRITER}, so the registry may gain an entry from a "
            f"path that was never indexed: {sorted(sites)}"
        )

    def test_the_registry_has_exactly_one_writer_in_the_server_package(self):
        """The other half of the same property, from the file side.

        The route walk above starts at handlers. This starts at the source and
        enumerates every function in the package that writes projects.json, so
        a writer added somewhere no route reaches yet is still visible the day
        it lands rather than the day something calls it.

        Scoped to the server package deliberately. clean-rag/fix_boat_bug.py
        also writes the file and is not a defect: see the note in
        app._registered_project_or_error for why an operator run CLI that only
        removes entries does not reopen this.
        """
        writers = _registry_writers_in_package()
        adding = [w for w in writers if w not in _REMOVAL_ONLY_WRITERS]

        assert adding == ["indexing.py:_update_project_registry"], (
            "state/projects.json has a writer other than the indexing "
            f"pipeline, so registry membership no longer means the server "
            f"indexed the directory: {adding}"
        )

        # A name on the removal allowlist that no longer writes the file at all
        # is a stale exemption. Left in place it silently approves in advance
        # whatever a future function of that name does.
        stale = set(_REMOVAL_ONLY_WRITERS) - set(writers)
        assert not stale, (
            f"these are allowlisted as removal only writers but no longer "
            f"write state/projects.json, so the exemption is stale and should "
            f"be deleted: {sorted(stale)}"
        )

    def test_a_removal_only_writer_really_cannot_add(self):
        """The allowlist has to be earned, not asserted.

        _REMOVAL_ONLY_WRITERS excuses a function from the one writer rule on
        the grounds that it can only take entries out. Nothing checked that.
        A name on a list is exactly the inert assertion the class docstring
        above warns about: it pins a name, and the identical hole reopens the
        day that function grows an assignment.

        So this reads each allowlisted function's source and fails if it can
        put an entry into a mapping at all. Adding `registry[pid] = entry` to
        _remove_from_project_registry has to turn this red.
        """
        package_dir = Path(app_mod.__file__).parent
        offenders = {}

        for site in sorted(_REMOVAL_ONLY_WRITERS):
            filename, func_name = site.split(":", 1)
            tree = ast.parse((package_dir / filename).read_text(encoding="utf-8"))
            found = [
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == func_name
            ]
            assert found, (
                f"{site} is on the removal only allowlist but no such function "
                f"exists, so the exemption protects nothing"
            )
            for node in found:
                if _can_add_a_registry_entry(node):
                    offenders[site] = "assigns into a mapping"

        assert not offenders, (
            "a function allowlisted as removal only can add an entry to "
            "state/projects.json, which is the exec route allowlist. That is "
            f"the self service registration hole reopening: {offenders}"
        )

    def test_indexing_refuses_a_path_that_is_not_a_directory(self, tmp_path):
        """The half that makes removing the other route enough.

        Indexing is the only remaining way into the registry, so it has to be
        the one that cannot be told to register a path that is not there. The
        reproduction that motivated this did not need the directory to exist
        when it registered, only by the time /run-tests ran.
        """
        ghost = tmp_path / "does-not-exist"

        response = asyncio.run(
            app_mod.handle_index_project(_StubRequest({"project_path": str(ghost)}))
        )

        assert response.status == 400, (
            "indexing accepted a path that is not a directory, so the registry "
            "can name somewhere nothing has ever been read from"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
