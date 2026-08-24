"""Make this suite report honestly when pytest-asyncio is not installed.

27 tests here are async and carry @pytest.mark.asyncio. Without the plugin
pytest does not skip them, it fails them, and the only clue is a warning that
reads like a typo:

    PytestUnknownMarkWarning: Unknown pytest.mark.asyncio, is this a typo?

So a correct checkout reported 27 failures caused entirely by a missing test
dependency, which is indistinguishable at a glance from 27 real bugs. A suite
that cries wolf gets ignored, and this one was: the failures sat there long
enough to be assumed normal.

This registers the marker (killing the misleading warning) and converts those
tests into skips that name the fix. Nothing changes when the plugin IS
installed: it claims the marker first and these tests run for real.

See requirements-dev.txt.
"""
import pytest

_INSTALL_HINT = (
    "pytest-asyncio is not installed, so async tests cannot run. "
    "Install it with: clean-rag/clean-rag-venv/bin/python -m pip install "
    "-r clean-rag/requirements-dev.txt"
)


def _asyncio_plugin_active(config) -> bool:
    """True when pytest-asyncio is present to handle the marker."""
    pm = config.pluginmanager
    return bool(pm.hasplugin("asyncio") or pm.hasplugin("pytest_asyncio"))


def pytest_configure(config):
    # Registering it removes the "unknown mark, is this a typo" warning, which
    # pointed at the test file rather than at the absent package.
    config.addinivalue_line(
        "markers",
        "asyncio: async test, requires pytest-asyncio (see requirements-dev.txt)",
    )


def pytest_collection_modifyitems(config, items):
    if _asyncio_plugin_active(config):
        return

    skip = pytest.mark.skip(reason=_INSTALL_HINT)
    skipped = 0
    for item in items:
        if item.get_closest_marker("asyncio"):
            item.add_marker(skip)
            skipped += 1

    if skipped:
        config.stash.setdefault(_COUNT_KEY, 0)
        config.stash[_COUNT_KEY] = skipped


_COUNT_KEY = pytest.StashKey[int]()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Say it once, plainly, at the end rather than only per test."""
    count = config.stash.get(_COUNT_KEY, 0)
    if count:
        terminalreporter.write_sep(
            "-", f"{count} async test(s) skipped: pytest-asyncio not installed"
        )
        terminalreporter.write_line(
            "  clean-rag/clean-rag-venv/bin/python -m pip install "
            "-r clean-rag/requirements-dev.txt"
        )
