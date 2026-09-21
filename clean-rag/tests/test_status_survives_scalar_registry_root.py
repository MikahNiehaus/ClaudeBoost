"""bad-cop adversarial: /status must not 500 on a scalar registry root.

The prior round's fix made ``_with_files_total`` pass a non dict registry
root through unchanged, on the reasoning that "the reply that still carries
the other fields beats a 500" (app.py, ``_with_files_total`` docstring). That
holds for a list or a string root, both of which support ``len()``. It does
not hold for ``int``, ``float``, ``bool`` or ``None``: ``handle_status`` calls
``len(projects)`` unconditionally at app.py:249, and none of those four types
define ``__len__``, so the exact bug class this round claims to have closed
(one malformed ``state/projects.json`` root turning ``/status`` into a 500 for
every project) is still reachable through them.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import app as app_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_model_state():
    orig_cache = app_mod._model_cache
    orig_error = app_mod._warmup_error
    app_mod._model_cache = None
    app_mod._warmup_error = None
    yield
    app_mod._model_cache = orig_cache
    app_mod._warmup_error = orig_error


@pytest.mark.parametrize("bad_root", [7, None, 3.14, True])
def test_status_does_not_500_on_a_scalar_registry_root(bad_root, monkeypatch):
    monkeypatch.setattr(app_mod, "_list_projects", lambda: bad_root)
    result = asyncio.run(app_mod.handle_status(MagicMock()))
    assert result.status == 200
