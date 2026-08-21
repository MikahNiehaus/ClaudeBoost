"""Adversarial tests for cli/reindex_batch.py's stop path and reindex_unit.py's
incremental plan cost.

Originally written by bad-cop to prove two defects:

  1. ``--stop`` could not interrupt an in-flight ``index_project``. The only
     ``should_abort`` the batch driver ever passed was ``checkpoint.pressure``,
     which knows nothing about the stop file, so the flag did nothing for as
     long as one project took (hours, on the largest registered project).
  2. ``project_model(for_rebuild=False)`` fell back to ``routed_model``, so the
     unattended hourly sweep paid a full directory walk per unprovenanced
     project -- measured 0.0372s vs 0.0001s on 400 files -- for an answer
     ``find_changed_files`` then discarded by returning early on the missing
     manifest.

Inverted here to assert the corrected behaviour, keeping the same attacks: the
stop file still appears mid-flight from "another terminal", and the plan is
still asked to order projects that have never been indexed.

Everything is pinned to tmp_path. Nothing here touches the real registry, the
real DATABASES_DIR, the real state directory, or the clean-rag server.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class StubEmbedder:
    model_name = "stub-embedder"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] for _ in texts]

    def embed_query(self, text):
        return [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]


def _make_project(root: Path, n_files: int) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for f in range(n_files):
        body = "\n".join(
            f'''
def handler_{f}_{i}(payload, retries=3):
    """Process one payload and return a normalised record."""
    total = 0
    for index, item in enumerate(payload.get("items", [])):
        if item.get("skip"):
            continue
        total += int(item.get("amount", 0)) * (index + 1)
    if total > 1000 and retries > 0:
        return handler_{f}_{i}({{"items": []}}, retries - 1)
    return {{"total": total, "count": len(payload.get("items", []))}}
'''
            for i in range(12)
        )
        (root / f"module_{f:02d}.py").write_text(body, encoding="utf-8")
    return root


@pytest.fixture()
def batch(tmp_path):
    """cli/reindex_batch.py with its state directory pinned at tmp_path.

    Loaded fresh per test so patching its module globals cannot leak, and so a
    test can never write reindex-progress.json or reindex-STOP into the real
    clean-rag/state/.
    """
    mod = _load_module("reindex_batch_under_test", CLEAN_RAG / "cli" / "reindex_batch.py")
    mod.STATE_DIR = tmp_path / "batch-state"
    mod.STATE_DIR.mkdir(parents=True, exist_ok=True)
    mod.PROGRESS = mod.STATE_DIR / "reindex-progress.json"
    mod.STOP_FILE = mod.STATE_DIR / "reindex-STOP"
    return mod


@pytest.fixture()
def isolated_indexing(tmp_path, monkeypatch):
    """indexing.py pinned at temp dirs, so index_project cannot write into the
    real databases/_projects/ or register a throwaway project."""
    from server import indexing

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    return indexing


def _manifest_files(indexing, project: Path) -> set[str]:
    *_, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {k for k in raw if not k.startswith("__")}


class _ScriptedCheckpoint:
    """A PressureCheckpoint stand-in with a scripted pressure sequence."""

    def __init__(self, reasons=(), on_call=None):
        self._reasons = list(reasons)
        self._on_call = on_call
        self.calls = 0

    def pressure(self):
        self.calls += 1
        if self._on_call is not None:
            self._on_call(self.calls)
        return self._reasons.pop(0) if self._reasons else None


# ---------------------------------------------------------------------------
# Finding 1: --stop must be observed during a single index_project call.
# ---------------------------------------------------------------------------

def test_abort_check_reports_a_stop_that_appears_mid_flight(batch):
    """The abort callable index_project is actually given must go truthy the
    moment the stop file appears, not at the next attempt hours later.

    Same attack bad-cop used: call should_abort repeatedly the way
    index_project's per file loop does, and create the stop file halfway
    through, exactly as a user running --stop from another terminal would.
    """
    checkpoint = _ScriptedCheckpoint()  # never any pressure
    should_abort = batch.abort_check(checkpoint)

    reasons = []
    for i in range(10):
        if i == 5:
            batch.STOP_FILE.write_text("stop requested\n", encoding="utf-8")
        reasons.append(should_abort())

    assert reasons[:5] == [None] * 5, (
        f"aborted before the stop file existed and with no pressure: {reasons[:5]}"
    )
    assert reasons[5:] == [batch.STOP_REASON] * 5, (
        f"the stop file appeared at call 6 and should_abort still would not "
        f"stop the run: {reasons[5:]}"
    )


def test_a_stop_reason_is_distinguishable_from_a_pressure_pause(batch):
    """A stop and a pressure pause mean opposite things about what happens
    next, so index_project must record them as different reasons."""
    pressure_reason = "CPU 95% (limit 80%)"
    checkpoint = _ScriptedCheckpoint(reasons=[pressure_reason] * 4)
    should_abort = batch.abort_check(checkpoint)

    assert should_abort() == pressure_reason, (
        "with no stop file the abort must still report real resource pressure"
    )

    batch.STOP_FILE.write_text("stop requested\n", encoding="utf-8")
    stop = should_abort()

    assert stop == batch.STOP_REASON
    assert stop != pressure_reason, (
        "a stop that reads as a pressure pause would be retried as though the "
        "machine had merely got busy"
    )


def test_stop_halts_a_real_index_at_the_next_file_and_stays_resumable(
    batch, isolated_indexing, tmp_path
):
    """End to end through the real index_project: a stop raised while file 2 is
    being embedded stops the run at file 3, and what it leaves behind is a
    truthful, resumable subset rather than a discarded or half written index.
    """
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=6)

    def stop_during_second_file(call_n):
        # The user runs --stop from another terminal while file 2 is in flight.
        if call_n == 2:
            batch.STOP_FILE.write_text("stop requested\n", encoding="utf-8")

    checkpoint = _ScriptedCheckpoint(on_call=stop_during_second_file)
    result = indexing.index_project(
        str(project), StubEmbedder(), force=True,
        should_abort=batch.abort_check(checkpoint),
    )

    assert result["files_indexed"] == 2, (
        f"indexed {result['files_indexed']} files; the stop landed during the "
        f"2nd file so the 3rd per file check should have ended the run"
    )
    assert result["stopped_early"] == batch.STOP_REASON
    assert result["chunks_created"] > 0, "test setup: nothing was actually indexed"

    # Resumable, not discarded: the manifest names exactly the files whose
    # chunks are really in the store, and says plainly that it is partial.
    assert _manifest_files(indexing, project) == {"module_00.py", "module_01.py"}
    assert indexing.index_is_incomplete(str(project)) is True

    # And a later run really does pick up where the stop left off.
    resumed = indexing.index_project(str(project), StubEmbedder(), force=False)
    assert resumed["files_indexed"] == 4
    assert resumed["files_unchanged"] == 2
    assert _manifest_files(indexing, project) == {
        f"module_{i:02d}.py" for i in range(6)
    }
    assert indexing.index_is_incomplete(str(project)) is False


@pytest.mark.asyncio
async def test_stopped_project_is_not_recorded_as_a_failure(batch, monkeypatch):
    """--stop is a request the driver honoured, not a project that failed.

    Recording it under "failed" would give --stop a nonzero exit code and, on
    the next run, report a project as broken when it is merely part indexed.
    """
    from server.reindex_unit import PlannedProject

    project = PlannedProject(pid="pid0", path=str(batch.STATE_DIR), model="m", size=3)

    async def headroom(*_a, **_k):
        return True

    def index_project_that_gets_stopped(path, cache, force=False, should_abort=None):
        batch.STOP_FILE.write_text("stop requested\n", encoding="utf-8")
        assert should_abort() == batch.STOP_REASON
        return {"files_indexed": 2, "chunks_created": 7,
                "stopped_early": batch.STOP_REASON}

    monkeypatch.setattr(batch, "plan_sweep", lambda **_k: [project])
    monkeypatch.setattr(batch, "wait_for_system_headroom", headroom)
    monkeypatch.setattr(batch, "index_project", index_project_that_gets_stopped)
    monkeypatch.setattr(batch, "index_is_incomplete", lambda _p: False)
    monkeypatch.setattr(batch, "acquire_index_lock", lambda *_a: True)
    monkeypatch.setattr(batch, "release_index_lock", lambda: None)

    exit_code = await batch.run()

    assert exit_code == 0, "a run the user stopped is not a failed run"
    state = json.loads(batch.PROGRESS.read_text(encoding="utf-8"))
    assert state["failed"] == {}, (
        f"the stopped project was recorded as a failure: {state['failed']}"
    )
    assert state["done"] == {}, "a part indexed project must not be marked done"


def test_unreadable_progress_is_reported_not_swallowed(batch, capsys):
    """Falling back to "start over" on a corrupt progress file is right; doing
    it silently is not, because it looks exactly like a first run while quietly
    re-indexing every project that was already finished."""
    batch.PROGRESS.write_text("{not json", encoding="utf-8")

    assert batch.load_progress() == {"done": {}, "failed": {}}
    out = capsys.readouterr().out
    assert "could not read" in out and str(batch.PROGRESS) in out, (
        f"a corrupt progress file was discarded without a word: {out!r}"
    )


@pytest.mark.asyncio
async def test_a_stop_is_not_retried_as_a_pressure_pause(batch, monkeypatch, capsys):
    """A stop leaves the same __incomplete__ manifest a pressure pause does, so
    the driver has to tell them apart by the reason, not by the manifest.

    Treating it as a pause meant a project the user stopped was logged as
    "paused", counted against the pause budget, and slept RETRY_FLOOR_S before
    a retry that the loop head would refuse anyway.
    """
    from server.reindex_unit import Outcome, PlannedProject

    project = PlannedProject(pid="pid0", path=str(batch.STATE_DIR), model="m", size=3)
    attempts = {"n": 0}

    async def headroom(*_a, **_k):
        return True

    def index_project_that_gets_stopped(path, cache, force=False, should_abort=None):
        attempts["n"] += 1
        batch.STOP_FILE.write_text("stop requested\n", encoding="utf-8")
        return {"files_indexed": 2, "chunks_created": 7,
                "stopped_early": batch.STOP_REASON}

    monkeypatch.setattr(batch, "wait_for_system_headroom", headroom)
    monkeypatch.setattr(batch, "index_project", index_project_that_gets_stopped)
    # What index_project really leaves behind after any early stop.
    monkeypatch.setattr(batch, "index_is_incomplete", lambda _p: True)
    monkeypatch.setattr(batch, "acquire_index_lock", lambda *_a: True)
    monkeypatch.setattr(batch, "release_index_lock", lambda: None)

    outcome, result = await batch.reindex_project_fully(
        project, object(), batch.PressureCheckpoint()
    )

    assert outcome is Outcome.GAVE_UP
    assert attempts["n"] == 1
    assert result["stopped_early"] == batch.STOP_REASON
    assert "paused" not in capsys.readouterr().out, (
        "a stop was reported as a resource pause, which reads as 'retry when "
        "the machine is quiet' for something the user asked to end"
    )


# ---------------------------------------------------------------------------
# Finding 2: the incremental sweep must not walk the tree.
# ---------------------------------------------------------------------------

def test_incremental_plan_never_walks_an_unprovenanced_project(tmp_path, monkeypatch):
    """plan_sweep(for_rebuild=False) must cost zero directory walks even when
    no project has recorded provenance, because that is the unattended hourly
    path and the walk bought nothing: find_changed_files returns early on the
    missing manifest without scanning at all.

    The rebuild path must keep walking, because it genuinely needs the routed
    model and takes an exact file count from the same walk.
    """
    from server import auto_reindex, file_scan, indexing, reindex_unit

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")

    scanned = {"files": 0, "walks": 0}
    real_scan_project = file_scan.scan_project

    def counting_scan_project(path):
        result = list(real_scan_project(path))
        scanned["walks"] += 1
        scanned["files"] += len(result)
        return result

    # routed_model does `from .file_scan import scan_project` inside its body,
    # so the module attribute is what it picks up. auto_reindex bound the name
    # at import, so it needs patching separately for its count to mean anything.
    monkeypatch.setattr(file_scan, "scan_project", counting_scan_project)
    monkeypatch.setattr(auto_reindex, "scan_project", counting_scan_project)

    registry = {}
    for i in range(3):
        proj = _make_project(tmp_path / f"proj_{i}", n_files=40)
        registry[f"pid_{i}"] = {"project_path": str(proj), "files_indexed": 40}

    plan = reindex_unit.plan_sweep(registry, for_rebuild=False)

    assert len(plan) == 3
    assert scanned["walks"] == 0, (
        f"the hourly sweep walked {scanned['walks']} project tree(s) "
        f"({scanned['files']} files) to plan work it will not do"
    )

    # All three share one group, so the sweep visits them contiguously instead
    # of interleaving them among real model groups.
    assert reindex_unit.model_groups(plan) == [(None, plan)]

    # The walk really would have bought nothing: this is the function that
    # decides what the sweep does, and it never reaches scan_project.
    changed, deleted = auto_reindex.find_changed_files(plan[0].path)
    assert (changed, deleted) == ([], [])
    assert scanned["walks"] == 0

    # The rebuild path still walks, once per project, and gets exact counts.
    monkeypatch.setattr(
        reindex_unit, "get_model_for_project", lambda counts: "routed/model",
        raising=False,
    )
    rebuild = reindex_unit.plan_sweep(registry, for_rebuild=True)
    assert scanned["walks"] == 3, (
        f"the rebuild path must keep its walk; saw {scanned['walks']}"
    )
    assert [p.size for p in rebuild] == [40, 40, 40]
    assert all(p.size_is_estimate is False for p in rebuild)
