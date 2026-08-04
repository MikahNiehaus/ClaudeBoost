"""Does an interrupted MDB-MCP clone recover on the next run?

Invariant (the task's P6): a failed or interrupted clone of MDB-MCP must not
permanently wedge native-debugger registration, and must never leave state
that blocks all future runs. The next run of the installer has to clean up
the broken directory and retry, with no manual `rm -rf` from the user.

bad-cop's original version of this file asserted the *observed bug* instead of
that invariant (`assert result_second is None`, "the directory is permanently
wedged"), so it went green on the broken code and would have gone red on any
correct fix. Rewritten here to assert the contract the property states. The
failure mode it reproduces is unchanged and still real: git refuses a
destination that exists and is not empty.

Everything below is real execution — a real `git clone` subprocess against a
real local git repository created in a temp directory, so there is no network
dependency and no simulation of git's behavior. CLAUDE_DIR is redirected at a
temp path so the real ~/.claude is never touched.
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load(rel):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(rel.replace("/", "_").replace(".", "_"), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _make_origin(tmp: Path) -> Path:
    """A real one-commit git repo that looks like MDB-MCP (it has server.py)."""
    origin = tmp / "origin"
    origin.mkdir()
    (origin / "server.py").write_text("# stand-in for MDB-MCP's stdio server\n")
    (origin / "README.md").write_text("MDB-MCP\n")
    _git("init", "-q", "-b", "main", cwd=origin)
    _git("add", "-A", cwd=origin)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init", cwd=origin)
    return origin


def _prepare(setup_mod, tmp: Path, repo_uri: str):
    """Point setup.py at a temp ~/.claude and a local repo; count git clones.

    run_cmd stays real for git. Only the `import mcp, pygdbmi` dependency
    probe is short-circuited, so the test never shells out to pip.
    """
    setup_mod.CLAUDE_DIR = tmp / ".claude"
    setup_mod.MDB_MCP_REPO = repo_uri

    real_run_cmd = setup_mod.run_cmd
    clones = []

    def run_cmd(args):
        if args[:2] == [sys.executable, "-c"]:
            return 0, ""
        if args[:2] == ["git", "clone"]:
            clones.append(args)
        return real_run_cmd(args)

    setup_mod.run_cmd = run_cmd
    return clones


def test_interrupted_clone_recovers_on_the_next_run():
    """The leftover of a dropped clone must not block registration forever."""
    setup_mod = _load("scripts/setup.py")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clones = _prepare(setup_mod, tmp, _make_origin(tmp).as_uri())

        dest = setup_mod.CLAUDE_DIR / "mcp-servers" / "MDB-MCP"
        dest.mkdir(parents=True)
        # Exactly what a dropped connection leaves behind: git got partway in
        # and never finished, so there are files but no server.py.
        (dest / ".git").mkdir()
        (dest / "README.md").write_text("partial clone leftover")
        assert not (dest / "server.py").exists()

        result = setup_mod._mdb_mcp_server()
        print("result:", result)
        print("server.py present after retry:", (dest / "server.py").exists())

        assert result == [sys.executable, str(dest / "server.py")], (
            "the interrupted clone did not recover: _mdb_mcp_server must clear "
            f"the broken checkout and re-clone, got {result!r}")
        assert (dest / "server.py").is_file()
        assert not (dest / "README.md").read_text().startswith("partial"), (
            "the leftover files survived, so the checkout is a mix of two clones")
        assert len(clones) == 1, f"expected exactly one clone, got {clones}"


def test_leftover_staging_directory_does_not_block_the_clone():
    """A run killed mid-clone leaves the staging dir; it must be swept, not kept."""
    setup_mod = _load("scripts/setup.py")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _prepare(setup_mod, tmp, _make_origin(tmp).as_uri())

        dest = setup_mod.CLAUDE_DIR / "mcp-servers" / "MDB-MCP"
        staging = dest.parent / ".MDB-MCP-clone"
        staging.mkdir(parents=True)
        (staging / "half-written.txt").write_text("killed mid-clone")

        result = setup_mod._mdb_mcp_server()
        leftovers = sorted(p.name for p in dest.parent.iterdir())
        print("result:", result)
        print("mcp-servers/ contents:", leftovers)

        assert result == [sys.executable, str(dest / "server.py")]
        assert leftovers == ["MDB-MCP"], f"staging junk survived: {leftovers}"


def test_second_run_reuses_the_clone_instead_of_recloning():
    """P2 idempotence: a good checkout is never removed or re-cloned."""
    setup_mod = _load("scripts/setup.py")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        clones = _prepare(setup_mod, tmp, _make_origin(tmp).as_uri())

        first = setup_mod._mdb_mcp_server()
        second = setup_mod._mdb_mcp_server()
        print("first:", first)
        print("second:", second)
        print("clone count:", len(clones))

        assert first == second is not None
        assert len(clones) == 1, f"re-cloned an already-good checkout: {clones}"


def test_failed_clone_leaves_no_state_that_blocks_the_next_run():
    """P6's other half: a clone that fails must not create the wedged dir."""
    setup_mod = _load("scripts/setup.py")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        origin = _make_origin(tmp)
        clones = _prepare(setup_mod, tmp, (tmp / "does-not-exist").as_uri())

        dest = setup_mod.CLAUDE_DIR / "mcp-servers" / "MDB-MCP"

        failed = setup_mod._mdb_mcp_server()
        leftovers = sorted(p.name for p in dest.parent.iterdir()) if dest.parent.is_dir() else []
        print("failed run:", failed)
        print("left behind in mcp-servers/:", leftovers)

        assert failed is None, "a clone against a nonexistent repo must fail soft"
        assert not dest.exists(), f"the failed clone left {dest} behind"
        assert leftovers == [], f"the failed clone left staging junk: {leftovers}"

        # And the very next run, once the repo is reachable, still succeeds.
        setup_mod.MDB_MCP_REPO = origin.as_uri()
        recovered = setup_mod._mdb_mcp_server()
        print("recovered run:", recovered)
        assert recovered == [sys.executable, str(dest / "server.py")]
        assert len(clones) == 2
