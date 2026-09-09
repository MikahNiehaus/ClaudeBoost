"""Measures the residual /index-project -> /run-tests chain.

/index-project deliberately takes project_path from a request body with no
allowlist, since registering a new path is its entire purpose. That means
anything that can reach this server can point /index-project at a directory of
its own choosing, then call /run-tests against the same path and have its
package.json test script executed as an operator registered project. This file
measures what that costs, rather than assuming the principle is the whole
answer, and it is a measurement rather than a fix on purpose: the tradeoffs and
the deferral are written up in
spec/architecture-addons/server-exec-route-capability-boundary.md.

It also holds the check that the reachability test guarding the registry is not
inert, which is a different question from whether it passes.

Isolation, the fixtures and the request stub are imported from
test_exec_routes_require_registered_project rather than restated here. One
definition means one place to fix when it turns out to be incomplete, which is
what happened to the version that patched app.STATE_DIR and left
indexing.STATE_DIR pointed at the operator's real directory.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app as app_mod  # noqa: E402
from tests.test_exec_routes_require_registered_project import (  # noqa: E402
    _OfflineEmbedder,
    _StubRequest,
    _attacker_project,
    _real_tree_bindings,
    _routes_reaching_a_registry_writer,
    empty_registry,  # noqa: F401  (used as a fixture by name)
)


def test_the_shared_fixture_leaves_nothing_pointed_at_real_state(
    empty_registry, tmp_path,
):
    """The fixture's isolation is a property, so assert it rather than trust it.

    Two ways it has actually failed, both of them silent. ``from .config import
    STATE_DIR`` copies the binding, so repointing the module whose handler is
    under test leaves the module that does the writing untouched. And a
    constant derived from STATE_DIR at import, such as
    indexing._INDEX_LOCK_PATH, does not move when STATE_DIR is repointed after
    it, so a test taking the index lock wrote a real file into the operator's
    state directory and contended with the running server for it.

    Checks the outcome rather than the mechanism, so it survives the fixture
    changing how it repoints things.
    """
    stragglers = [
        f"{module.__name__}.{attr} = {value}"
        for module, attr, value, _ in _real_tree_bindings()
    ]
    assert not stragglers, (
        f"these resolve into the operator's own directories while a test "
        f"fixture is active: {stragglers}"
    )


def test_a_renamed_registry_writing_route_is_caught(empty_registry, tmp_path):
    """Confirms the reachability check bites, which passing does not show.

    The assertion this replaced read ``"/register-project" not in served``. It
    was green against an app serving a route that wrote the registry from a
    request body under any other name, so it certified the property while
    catching nothing. A test that guards a property has to fail when the
    property is violated, not when one spelling of the violation appears, so
    the violation is constructed here and the guard is required to see it.

    The handler body is the deleted route's own, from git history: read the
    registry, add an entry built from the request body, resolve
    ``STATE_DIR / "projects.json"`` and write it back. Copying the real shape
    matters, because a violation invented to suit the checker proves only that
    the checker recognises inventions.
    """
    from aiohttp import web

    async def mint_an_entry(request):
        body = await request.json()
        registry = app_mod._list_projects()
        registry["ext_minted"] = {
            "project_path": body["project_path"], "source": "external",
        }
        registry_path = app_mod.STATE_DIR / "projects.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        return web.json_response({"registered": "ext_minted"})

    app = app_mod.create_app()
    app.router.add_post("/reregister-project", mint_an_entry)

    reaching = _routes_reaching_a_registry_writer(app)

    assert "/reregister-project" in reaching, (
        "the reachability check did not see a route that writes "
        "state/projects.json straight from a request body, so it would not "
        "catch the hole reopening under a new name either"
    )
    assert "/index-project" in reaching, (
        "the legitimate writer stopped being visible, which means the check "
        "went blind rather than becoming strict"
    )


def test_index_project_then_run_tests_executes_attacker_code(
    empty_registry, tmp_path, monkeypatch,
):
    """The residual chain, driven end to end in a scratch tree.

    Proves it is real rather than theoretical, and measures what it costs:
    wall clock time, and whether indexing has to recognise any of the
    attacker's files as code for the path to still be registered.
    """
    monkeypatch.setattr(app_mod, "_model_cache", _OfflineEmbedder())
    project = _attacker_project(tmp_path / "attacker-project")

    start = time.time()
    index_result = asyncio.run(
        app_mod.handle_index_project(_StubRequest({"project_path": str(project)}))
    )
    elapsed = time.time() - start

    assert index_result.status == 200, json.loads(index_result.body)
    index_body = json.loads(index_result.body.decode("utf-8"))

    registry_path = empty_registry / "projects.json"
    assert registry_path.exists(), "index-project did not write the scratch registry"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registered = {
        str(Path(entry["project_path"]).resolve()) for entry in registry.values()
    }
    assert str(project.resolve()) in registered, (
        "the attacker's own directory was not registered by indexing it"
    )

    run_result = asyncio.run(
        app_mod.handle_run_tests(_StubRequest({"project_path": str(project)}))
    )
    assert run_result.status == 200, json.loads(run_result.body)
    run_body = json.loads(run_result.body.decode("utf-8"))

    assert (project / "PWNED.txt").exists(), (
        "the attacker's package.json test script did not run, so the chain "
        "index-project(attacker dir) -> run-tests(same dir) executed nothing"
    )

    print(
        f"\n[measured] index-project(1 code file) -> run-tests round trip: "
        f"{elapsed:.3f}s to become a registered, runnable project. "
        f"files_indexed={index_body.get('files_indexed')} "
        f"run_summary={run_body.get('summary')!r}"
    )


def test_index_project_registers_even_with_zero_indexable_files(
    empty_registry, tmp_path, monkeypatch,
):
    """Quantifies the actual bar.

    Does the directory have to contain anything indexing.py recognises as
    code, or does registration happen regardless of files_indexed?
    package.json is not a CODE_EXTENSIONS member, so a bare scripts.test entry
    with nothing else is the smallest payload. Registration at
    files_indexed == 0 means the cost is not "have a codebase", it is one JSON
    file naming a command.
    """
    monkeypatch.setattr(app_mod, "_model_cache", _OfflineEmbedder())
    project = tmp_path / "minimal-attacker"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({
            "name": "minimal",
            "scripts": {"test": "node -e \"require('fs').writeFileSync('PWNED.txt','x')\""},
        }),
        encoding="utf-8",
    )

    index_result = asyncio.run(
        app_mod.handle_index_project(_StubRequest({"project_path": str(project)}))
    )
    assert index_result.status == 200
    index_body = json.loads(index_result.body.decode("utf-8"))

    run_result = asyncio.run(
        app_mod.handle_run_tests(_StubRequest({"project_path": str(project)}))
    )
    assert run_result.status == 200, json.loads(run_result.body)

    print(
        f"\n[measured] files_indexed={index_body.get('files_indexed')} "
        f"was enough to register and then run tests: "
        f"{(project / 'PWNED.txt').exists()}"
    )
    assert (project / "PWNED.txt").exists()


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "-s"]))
