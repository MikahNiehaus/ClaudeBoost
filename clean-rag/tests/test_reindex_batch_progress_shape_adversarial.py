"""bad-cop adversarial: load_progress()'s narrowed except clause,
``(OSError, ValueError)``, only ever fires when ``PROGRESS.read_text`` or
``json.loads`` itself raises. A progress file that is syntactically valid
JSON but the wrong *shape* -- a list, a string, ``null``, a bare number, or a
dict missing "done"/"failed" -- raises nothing at all inside load_progress(),
so it passes straight through unchanged and reaches run() untouched.

run() immediately does ``m.pid in state["done"]`` while building the log
preview, which is reached even under ``--dry-run`` (the side-effect-free
preflight check this exact driver is about to be run as, on 16 registered
projects, right before a ~76 hour job). A non-dict state blows that up with
an uncaught TypeError before a single project is even considered.

This is the same fault class the round's fix targeted (an unhandled crash
from an unexpected progress file), just not the same trigger: this one is
valid JSON, not invalid bytes, so json.JSONDecodeError/UnicodeDecodeError
narrowing does nothing for it either way.

Everything here is pinned to tmp_path; nothing touches the real
clean-rag/state/reindex-progress.json.
"""
import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path("C:/Development/ClaudeBoost/clean-rag")
sys.path.insert(0, str(CLEAN_RAG))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def batch(tmp_path):
    mod = _load_module("reindex_batch_shape_test", CLEAN_RAG / "cli" / "reindex_batch.py")
    mod.STATE_DIR = tmp_path / "batch-state"
    mod.STATE_DIR.mkdir(parents=True, exist_ok=True)
    mod.PROGRESS = mod.STATE_DIR / "reindex-progress.json"
    mod.STOP_FILE = mod.STATE_DIR / "reindex-STOP"
    return mod


@pytest.mark.parametrize("payload", ["[1, 2, 3]", '"hello"', "null", "42", '{"other": 1}'])
def test_load_progress_normalises_a_wrong_shaped_file(batch, payload):
    """Valid JSON of the wrong TYPE must fall back, not pass through.

    It never raises inside load_progress, so no width of except clause catches
    it. The shape has to be checked explicitly or it reaches run() and blows up
    there instead.
    """
    batch.PROGRESS.write_text(payload, encoding="utf-8")
    assert batch.load_progress() == {"done": {}, "failed": {}}


@pytest.mark.parametrize(
    "payload",
    [
        '{"done": {}, "failed": {}}',
        '{"done": {"a": {"files": 1}}, "failed": {}}',
        '{"done": {}, "failed": {"b": "errored"}, "extra": "ignored"}',
    ],
)
def test_load_progress_keeps_a_genuinely_valid_file(batch, payload):
    """The guard must not throw away real progress. Getting this wrong silently
    re-indexes every finished project, which on this corpus is days."""
    import json

    batch.PROGRESS.write_text(payload, encoding="utf-8")
    assert batch.load_progress() == json.loads(payload)


@pytest.mark.parametrize("payload", ["[1, 2, 3]", '"hello"', "null", "42", '{"done": []}'])
def test_a_wrong_shaped_progress_file_does_not_crash_run(batch, payload):
    """--dry-run is the preflight before a multi day job. It must survive a
    junk progress file rather than die on `pid in state["done"]`."""
    from server.reindex_unit import PlannedProject

    batch.PROGRESS.write_text(payload, encoding="utf-8")

    project = PlannedProject(pid="pid0", path=str(batch.STATE_DIR), model="m", size=1)
    batch.plan_sweep = lambda **_k: [project]

    assert asyncio.run(batch.run(dry_run=True)) == 0


def test_dry_run_does_not_write_a_progress_file(batch):
    """A preflight that mutates state is not a preflight."""
    from server.reindex_unit import PlannedProject

    project = PlannedProject(pid="pid0", path=str(batch.STATE_DIR), model="m", size=1)
    batch.plan_sweep = lambda **_k: [project]

    assert asyncio.run(batch.run(dry_run=True)) == 0
    assert not batch.PROGRESS.exists()
