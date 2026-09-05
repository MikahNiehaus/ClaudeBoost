"""Tests for the resource limits the background reindex runs under:

  server/config.py       CPU_MAX_PERCENT, MIN_FREE_RAM_MB, TORCH_THREADS,
                          SWEEP_INTERVAL_S, CPU_BACKOFF_S, CPU_BACKOFF_MAX_WAIT_S
  server/embedding.py    _apply_torch_thread_cap()
  server/auto_reindex.py wait_for_system_headroom(), the overlap guard,
                          _release_project_resources()
  cli/server_ctl.py      STOP_MARKER_NAME, _mark_stopped_by_user(),
                          _clear_stopped_by_user()

Each test states the failure it is there to catch, so a later change that
reintroduces one fails here rather than in production.
"""
import asyncio
import importlib.util
import json
import logging
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))
sys.path.insert(0, str(CLEAN_RAG / "hooks"))
sys.path.insert(0, str(CLEAN_RAG / "cli"))


def _load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeAsyncioNamespace:
    """Wraps the real asyncio module but replaces `sleep`, so patching this
    onto auto_reindex's module-level `asyncio` name does not mutate the real,
    globally shared asyncio module (which would break every other coroutine
    on the same event loop, including pytest-asyncio's own machinery)."""

    def __init__(self, real_asyncio, sleep_fn):
        self._real = real_asyncio
        self._sleep_fn = sleep_fn

    def __getattr__(self, name):
        return getattr(self._real, name)

    async def sleep(self, s):
        return await self._sleep_fn(s)


@pytest.fixture()
def auto_reindex():
    from server import auto_reindex as mod
    # Reset module globals between tests -- they are plain module state.
    mod._sweep_in_progress = False
    mod._sweep_started_at = 0.0
    yield mod
    mod._sweep_in_progress = False
    mod._sweep_started_at = 0.0


@pytest.fixture()
def server_ctl():
    mod = _load_module("server_ctl_under_test", str(CLEAN_RAG / "cli" / "server_ctl.py"))
    return mod


# ---------------------------------------------------------------------------
# wait_for_system_headroom
# ---------------------------------------------------------------------------

class FakePsutil:
    """Deterministic stand-in for psutil, with a scripted cpu_percent sequence
    and a fixed available RAM figure."""

    def __init__(self, cpu_sequence, available_mb):
        self._cpu_sequence = list(cpu_sequence)
        self._calls = 0
        self.vm_calls = 0
        self._available_mb = available_mb

    def cpu_percent(self, interval=None):
        self._calls += 1
        if self._cpu_sequence:
            return self._cpu_sequence.pop(0)
        return 0.0

    def virtual_memory(self):
        self.vm_calls += 1
        vm = MagicMock()
        vm.available = self._available_mb * 1024 * 1024
        return vm


@pytest.mark.asyncio
async def test_headroom_returns_true_when_both_ok(auto_reindex):
    fake = FakePsutil(cpu_sequence=[999.0, 10.0], available_mb=8000)
    with patch.dict(sys.modules, {"psutil": fake}):
        result = await auto_reindex.wait_for_system_headroom(
            max_percent=80, min_free_ram_mb=3072, poll_s=0.01, max_wait_s=0.05,
        )
    assert result is True
    # The very first sample (999.0, a deliberately absurd "primer" value) must
    # never be read as the real measurement -- confirms the priming call is
    # actually thrown away, not just present in the source.
    assert fake._calls >= 2


@pytest.mark.asyncio
async def test_headroom_false_when_ram_starved_even_if_cpu_idle(auto_reindex):
    """This is the mutant-2 kill test: remove the RAM check, keep only CPU,
    and this must start failing."""
    fake = FakePsutil(cpu_sequence=[0.0, 1.0, 1.0, 1.0], available_mb=500)
    with patch.dict(sys.modules, {"psutil": fake}):
        result = await auto_reindex.wait_for_system_headroom(
            max_percent=80, min_free_ram_mb=3072, poll_s=0.01, max_wait_s=0.03,
        )
    assert result is False


class RealisticFakePsutil:
    """First call ever in the process returns a meaningless 0.0 (no prior
    sample), exactly like real psutil.cpu_percent(interval=None). Every call
    after that returns the real (scripted) load -- this is what actually
    distinguishes the priming call mattering from it being decorative."""

    def __init__(self, real_load_after_first, available_mb):
        self._first_call_done = False
        self._real_load = real_load_after_first
        self._available_mb = available_mb
        self.calls = 0

    def cpu_percent(self, interval=None):
        self.calls += 1
        if not self._first_call_done:
            self._first_call_done = True
            return 0.0
        return self._real_load

    def virtual_memory(self):
        vm = MagicMock()
        vm.available = self._available_mb * 1024 * 1024
        return vm


@pytest.mark.asyncio
async def test_mutant_remove_priming_reads_stale_zero_on_first_call(auto_reindex):
    """Mutant 7, run for real against the actual function (not a
    reimplementation): on a fresh process, psutil.cpu_percent(interval=None)'s
    first-ever call returns a meaningless 0.0. Prove the real code's priming
    call absorbs that, by feeding it a fake that reproduces the quirk and
    confirming the real measurement (95% CPU) is what actually gets acted on.
    """
    fake = RealisticFakePsutil(real_load_after_first=95.0, available_mb=8000)
    with patch.dict(sys.modules, {"psutil": fake}):
        result = await auto_reindex.wait_for_system_headroom(
            max_percent=80, min_free_ram_mb=3072, poll_s=0.01, max_wait_s=0.03,
        )
    assert result is False, (
        "machine is at 95% CPU but wait_for_system_headroom said there was "
        "headroom -- the priming call is not absorbing the meaningless "
        "first-call 0.0, so the first real reading is silently stale"
    )


@pytest.mark.asyncio
async def test_headroom_gives_up_after_max_wait(auto_reindex):
    fake = FakePsutil(cpu_sequence=[0.0] + [95.0] * 20, available_mb=8000)
    with patch.dict(sys.modules, {"psutil": fake}):
        start = time.monotonic()
        result = await auto_reindex.wait_for_system_headroom(
            max_percent=80, min_free_ram_mb=3072, poll_s=0.01, max_wait_s=0.03,
        )
        elapsed = time.monotonic() - start
    assert result is False
    assert elapsed < 1.0  # bounded, not stuck


@pytest.mark.asyncio
async def test_headroom_degrades_to_true_when_psutil_missing(auto_reindex):
    """Requirement 6: a missing dependency must not silently disable
    reindexing -- so it degrades to 'go ahead', not 'block forever'."""
    real_import = __import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *a, **kw)

    with patch("builtins.__import__", side_effect=fake_import):
        result = await auto_reindex.wait_for_system_headroom()
    assert result is True


def test_wait_for_cpu_headroom_is_still_the_same_function():
    """The alias is load-bearing: auto_reindex_loop's pre-sweep gate calls
    wait_for_cpu_headroom, so if the two ever drift apart the gate silently
    stops enforcing whatever the real one enforces."""
    from server import auto_reindex as mod

    assert mod.wait_for_cpu_headroom is mod.wait_for_system_headroom


# ---------------------------------------------------------------------------
# auto_reindex_loop: does a False return from the headroom check actually
# stop work, and does _sweep_in_progress get reset on every exit path
# including cancellation?
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_loop_skips_sweep_entirely_when_headroom_false(auto_reindex, monkeypatch, tmp_path):
    """If wait_for_cpu_headroom() (checked before the per-project loop even
    starts) returns False, no project must be swept this tick."""
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(json.dumps({"p1": {"project_path": str(tmp_path)}}))
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)

    sweep_calls = []

    async def fake_sweep_project(pid, entry, model_cache):
        sweep_calls.append(pid)

    async def headroom_false(*a, **kw):
        return False

    monkeypatch.setattr(auto_reindex, "_sweep_project", fake_sweep_project)
    monkeypatch.setattr(auto_reindex, "wait_for_cpu_headroom", headroom_false)

    sleep_calls = {"n": 0}

    async def fast_sleep(_s):
        sleep_calls["n"] += 1
        await asyncio.sleep(0)  # real yield, so this stays cooperative
        if sleep_calls["n"] > 1:
            raise asyncio.CancelledError()
        return None

    monkeypatch.setattr(auto_reindex, "asyncio", _FakeAsyncioNamespace(asyncio, fast_sleep))

    with pytest.raises(asyncio.CancelledError):
        await auto_reindex.auto_reindex_loop(lambda: object())

    assert sweep_calls == [], (
        "sweep ran even though wait_for_cpu_headroom() returned False -- "
        "the pre-loop headroom check is not actually consulted"
    )
    assert auto_reindex._sweep_in_progress is False


@pytest.mark.asyncio
async def test_loop_resets_overlap_flag_on_cancellation_mid_sweep(auto_reindex, monkeypatch, tmp_path):
    """Requirement 2 + the asyncio cancellation attack: if the task running
    auto_reindex_loop is cancelled while a sweep is in flight, the module
    global _sweep_in_progress must not be left stuck True, or every future
    tick skips forever with 'previous sweep still running'."""
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(json.dumps({"p1": {"project_path": str(tmp_path)}}))
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)

    async def headroom_true(*a, **kw):
        return True

    async def hanging_sweep(pid, entry, model_cache):
        # Simulate real cancellation arriving while a project sweep is
        # in flight (e.g. the server process is being shut down).
        await asyncio.sleep(3600)

    monkeypatch.setattr(auto_reindex, "wait_for_cpu_headroom", headroom_true)
    monkeypatch.setattr(auto_reindex, "_sweep_project", hanging_sweep)
    monkeypatch.setattr(auto_reindex, "_release_project_resources", lambda pid: None)

    async def instant_sleep(_s):
        await asyncio.sleep(0)
        return None

    monkeypatch.setattr(auto_reindex, "asyncio", _FakeAsyncioNamespace(asyncio, instant_sleep))

    task = asyncio.create_task(auto_reindex.auto_reindex_loop(lambda: object()))
    # Give the loop a tick to reach the hanging sweep and set the flag.
    for _ in range(50):
        await asyncio.sleep(0)
        if auto_reindex._sweep_in_progress:
            break
    assert auto_reindex._sweep_in_progress is True, "sweep never actually started"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert auto_reindex._sweep_in_progress is False, (
        "asyncio.CancelledError during a sweep left _sweep_in_progress stuck "
        "True -- every subsequent tick will skip forever"
    )


@pytest.mark.asyncio
async def test_pressure_is_rechecked_during_a_single_project_sweep(auto_reindex, monkeypatch, tmp_path):
    """The original finding, inverted to assert the fix.

    Headroom used to be consulted only BETWEEN projects, so one long-running
    project (the observed incident: 1293s for one 278-file project at
    ~4.65s/file, and a 4000+ file project extrapolates to hours) held the
    machine with no way to yield. _sweep_project must now hand index_project a
    live pressure check that index_project actually calls per file, and a
    machine that goes bad mid-project must stop the run part way.

    The fake index_project here is a stand-in for the real per-file loop (that
    one is exercised for real in
    test_index_project_stops_mid_project_when_pressure_appears); what is under
    test is that the sweep supplies a working check at all, and that a
    pressured machine really does cut the project short.
    """
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(json.dumps({"p1": {"project_path": str(tmp_path)}}))
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)

    total_files = 20
    files_done = {"n": 0}

    def fake_index_project(project_path, model_cache, force=False, should_abort=None):
        for _ in range(total_files):
            if should_abort is not None and should_abort():
                break
            files_done["n"] += 1
        return {"files_indexed": files_done["n"], "chunks_created": 0, "files_failed": 0}

    # 95% CPU: healthy when the sweep started, pressured by the time the
    # in-project checkpoint samples.
    fake_psutil = FakePsutil(cpu_sequence=[0.0] + [95.0] * 50, available_mb=8000)

    monkeypatch.setattr(auto_reindex, "index_project", fake_index_project)
    monkeypatch.setattr(auto_reindex, "find_changed_files",
                        lambda p: ([f"f{i}.py" for i in range(60)], []))
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **kw: True)
    monkeypatch.setattr(auto_reindex, "release_index_lock", lambda: None)
    monkeypatch.setattr(auto_reindex, "index_is_incomplete", lambda p: False)

    # interval_s=0 so every call really samples; the 15s production interval
    # would need a 15s test.
    checkpoint = auto_reindex.PressureCheckpoint(
        interval_s=0, max_percent=80, min_free_ram_mb=3072
    )

    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        await auto_reindex._sweep_project(
            "p1", {"project_path": str(tmp_path)}, object(), checkpoint=checkpoint
        )

    assert 0 < files_done["n"] < total_files, (
        f"indexed {files_done['n']} of {total_files} files -- a pressured "
        f"machine must cut a single project's index short, not run it to "
        f"completion (0 would mean it never started at all)"
    )


@pytest.mark.asyncio
async def test_healthy_machine_still_indexes_the_whole_project(auto_reindex, monkeypatch, tmp_path):
    """The other half: the checkpoint must not cost anything when there IS
    headroom. Same setup, idle machine, whole project must complete."""
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(json.dumps({"p1": {"project_path": str(tmp_path)}}))
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)

    total_files = 20
    files_done = {"n": 0}

    def fake_index_project(project_path, model_cache, force=False, should_abort=None):
        for _ in range(total_files):
            if should_abort is not None and should_abort():
                break
            files_done["n"] += 1
        return {"files_indexed": files_done["n"], "chunks_created": 0, "files_failed": 0}

    fake_psutil = FakePsutil(cpu_sequence=[0.0] + [5.0] * 50, available_mb=8000)

    monkeypatch.setattr(auto_reindex, "index_project", fake_index_project)
    monkeypatch.setattr(auto_reindex, "find_changed_files",
                        lambda p: ([f"f{i}.py" for i in range(60)], []))
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **kw: True)
    monkeypatch.setattr(auto_reindex, "release_index_lock", lambda: None)
    monkeypatch.setattr(auto_reindex, "index_is_incomplete", lambda p: False)

    checkpoint = auto_reindex.PressureCheckpoint(
        interval_s=0, max_percent=80, min_free_ram_mb=3072
    )

    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        await auto_reindex._sweep_project(
            "p1", {"project_path": str(tmp_path)}, object(), checkpoint=checkpoint
        )

    assert files_done["n"] == total_files, (
        "an idle machine must index the whole project; the new checkpoint "
        "changed behaviour when there was headroom"
    )


@pytest.mark.asyncio
async def test_incremental_loop_stops_part_way_under_pressure(auto_reindex, monkeypatch, tmp_path):
    """The per-file branch of _sweep_project (fewer than FULL_REINDEX_THRESHOLD
    changed files, nothing deleted) has the same hours-long exposure, one
    reindex_file at a time. It must consult the same checkpoint."""
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)

    reindexed = []
    monkeypatch.setattr(auto_reindex, "reindex_file",
                        lambda p, f, m: reindexed.append(f))
    monkeypatch.setattr(auto_reindex, "find_changed_files",
                        lambda p: ([f"f{i}.py" for i in range(10)], []))
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **kw: True)
    monkeypatch.setattr(auto_reindex, "release_index_lock", lambda: None)

    fake_psutil = FakePsutil(cpu_sequence=[0.0] + [95.0] * 50, available_mb=8000)
    checkpoint = auto_reindex.PressureCheckpoint(
        interval_s=0, max_percent=80, min_free_ram_mb=3072
    )

    with patch.dict(sys.modules, {"psutil": fake_psutil}):
        await auto_reindex._sweep_project(
            "p1", {"project_path": str(tmp_path)}, object(), checkpoint=checkpoint
        )

    assert len(reindexed) < 10, (
        f"reindexed all {len(reindexed)} changed files on a machine at 95% "
        f"CPU -- the per-file loop never checks for pressure"
    )


# ---------------------------------------------------------------------------
# index_project's own abort point, run for real against the real function on a
# real (tiny) project. No model is loaded: index_project accepts a plain
# embedder with an .embed() method, which is the backward-compat path
# auto_reindex already relies on.
# ---------------------------------------------------------------------------

class StubEmbedder:
    """Deterministic 8-dim vectors. Keeps this a test of the indexing loop, not
    of sentence-transformers."""

    model_name = "stub-embedder"

    def embed(self, texts):
        return [[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8] for _ in texts]


def _make_project(root: Path, n_files: int) -> Path:
    """A project of n_files real, chunkable Python files.

    Deliberately not a one-liner per file: the chunker drops anything under
    MIN_CHUNK_TOKENS, and a project that yields zero chunks would make every
    assertion below vacuously true.
    """
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
def isolated_indexing(tmp_path, monkeypatch):
    """indexing.py pinned at temp dirs.

    Without this, index_project writes into the real databases/_projects/ and
    registers the throwaway project in the real state/projects.json.
    """
    from server import indexing

    monkeypatch.setattr(indexing, "DATABASES_DIR", tmp_path / "databases")
    monkeypatch.setattr(indexing, "STATE_DIR", tmp_path / "state")
    return indexing


def _manifest_files(indexing, project: Path) -> set[str]:
    *_, manifest_path = indexing._project_paths(str(project))
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {k for k in raw if not k.startswith("__")}


def test_index_project_stops_mid_project_when_pressure_appears(isolated_indexing, tmp_path):
    """index_project used to run a whole project in one executor call with no
    way to yield. It must stop between files when the injected check says the
    machine is needed, and what it leaves behind must be coherent."""
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=6)

    seen = {"n": 0}

    def abort_after_two():
        seen["n"] += 1
        return "CPU 95% (limit 80%)" if seen["n"] > 2 else None

    result = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=abort_after_two
    )

    assert result["files_indexed"] == 2, (
        f"indexed {result['files_indexed']} files after the abort fired on the "
        f"3rd check -- index_project is not consulting should_abort per file"
    )
    assert result["stopped_early"] == "CPU 95% (limit 80%)"
    assert result["chunks_created"] > 0, "test setup: nothing was actually indexed"

    # Coherence: the manifest names exactly the files whose chunks are in the
    # store, and it says so honestly rather than reading as a finished index.
    assert len(_manifest_files(indexing, project)) == 2
    assert indexing.index_is_incomplete(str(project)) is True


def test_index_project_with_headroom_is_unchanged(isolated_indexing, tmp_path):
    """A check that never reports pressure must behave exactly like no check."""
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=6)

    with_check = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=lambda: None
    )
    assert with_check["files_indexed"] == 6
    assert "stopped_early" not in with_check
    assert indexing.index_is_incomplete(str(project)) is False

    without_check = indexing.index_project(str(project), StubEmbedder(), force=True)
    assert without_check["files_indexed"] == with_check["files_indexed"]
    assert without_check["chunks_created"] == with_check["chunks_created"]


def test_a_pressure_probe_that_raises_neither_stops_the_run_nor_hides_itself(
    isolated_indexing, tmp_path, caplog,
):
    """psutil can fail on a machine under real duress, and the manifest for
    everything embedded since the last checkpoint only exists in memory until
    the run ends. An exception out of the probe must therefore not end the run,
    and it must not pass silently either: unguarded is a state an operator has
    to be able to find out about."""
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=3)

    def exploding_probe():
        raise OSError("psutil could not read memory info")

    caplog.set_level(logging.ERROR)
    result = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=exploding_probe,
    )

    assert result["files_indexed"] == 3, (
        "a failed pressure read ended the run and discarded the work it had "
        "already embedded"
    )
    assert "stopped_early" not in result
    assert indexing.index_is_incomplete(str(project)) is False

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "OSError" in logged and "psutil could not read memory info" in logged, (
        f"the probe failure was swallowed without naming its cause: {logged!r}"
    )


def test_aborted_index_resumes_instead_of_starting_over(isolated_indexing, tmp_path):
    """An abort that could not be resumed would livelock: every sweep would
    redo the same first N files and never reach the end on a busy machine.
    The second pass must pick up the files the first one never reached."""
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=6)

    seen = {"n": 0}

    def abort_after_two():
        seen["n"] += 1
        return "free RAM 500 MB (need 3072 MB)" if seen["n"] > 2 else None

    first = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=abort_after_two
    )
    assert first["files_indexed"] == 2
    done_first = _manifest_files(indexing, project)

    # This is what _sweep_project does when index_is_incomplete() is True:
    # resume with force off so the finished files are kept.
    second = indexing.index_project(str(project), StubEmbedder(), force=False)

    assert second["files_indexed"] == 4, (
        f"resume re-embedded {second['files_indexed']} files; it should only "
        f"have done the 4 the abort never reached"
    )
    assert second["files_unchanged"] == 2
    assert _manifest_files(indexing, project) == {f"module_{i:02d}.py" for i in range(6)}
    assert done_first < _manifest_files(indexing, project)
    assert indexing.index_is_incomplete(str(project)) is False


def test_manual_retry_resumes_without_going_through_the_sweep_at_all(
    isolated_indexing, tmp_path,
):
    """.claude/commands/index-project.md's step 5 / lock section claims 'only
    the sweep's full rebuild branch ever resumes' an incomplete index, and
    that a project needs 50+ changed files in one sweep pass to get there.

    This calls index_project(force=False) directly, the exact call
    handle_index_project makes for a plain manual retry (server/app.py:546-548
    passes force=body.get('force', False)), with no auto_reindex module, no
    FULL_REINDEX_THRESHOLD, and no 'resuming' flag anywhere in the call path.
    If this resumes and clears __incomplete__, the doc's claim is false: a
    human does not need 50 changed files or the sweep at all, a second call to
    the same manual endpoint the doc itself documents in step 3 is sufficient.
    """
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=6)

    seen = {"n": 0}

    def abort_after_two():
        seen["n"] += 1
        return "free RAM 500 MB (need 4322 MB)" if seen["n"] > 2 else None

    first = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=abort_after_two
    )
    assert first["files_indexed"] == 2
    assert indexing.index_is_incomplete(str(project)) is True

    # The plain manual retry from step 3 of the doc: same function, force off,
    # no should_abort, nothing from auto_reindex.py involved.
    second = indexing.index_project(str(project), StubEmbedder(), force=False)

    assert second["files_indexed"] == 4, "the manual retry did not finish the project"
    assert indexing.index_is_incomplete(str(project)) is False, (
        "a plain manual /index-project retry (force off, no sweep, no 50-file "
        "threshold) cleared __incomplete__ on its own -- the doc's claim that "
        "'only the sweep's full rebuild branch ever resumes one' is "
        "contradicted by the real index_project() behaviour, which is the "
        "same behaviour the doc's own step 3 describes two sections earlier"
    )


def test_zero_files_indexed_stopped_early_registry_row_matches_the_docs_own_dead_row_test(
    isolated_indexing, tmp_path,
):
    """.claude/commands/index-project.md's new step 0 says a registry row is
    'dead' -- and should be deleted -- when files_indexed is 0 AND
    chunks_created is 0. _update_project_registry (indexing.py:1138-1168)
    writes exactly that shape for a run that stopped_early on the very first
    file, with indexed_at set to the current time (never null), because
    index_project calls _update_project_registry unconditionally regardless of
    stopped_early.

    So the same diff that adds the pressure guard makes the guard's own most
    aggressive outcome -- abort before file 1 on a busy machine -- produce a
    registry row indistinguishable, by the doc's own stated test, from a dead
    row that should be deleted. Deleting it does not touch the manifest or the
    chroma store, but it does drop the project from state/projects.json, which
    is what the sweep and rag-enforce's _has_real_index both read.
    """
    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=6)

    def abort_immediately():
        return "free RAM 100 MB (need 4322 MB)"

    result = indexing.index_project(
        str(project), StubEmbedder(), force=True, should_abort=abort_immediately,
    )

    assert result["files_indexed"] == 0
    assert result["chunks_created"] == 0
    assert result["stopped_early"] == "free RAM 100 MB (need 4322 MB)"
    # Genuinely resumable: the manifest and the guard agree this project is
    # incomplete, not empty.
    assert indexing.index_is_incomplete(str(project)) is True

    registry_path = indexing.STATE_DIR / "projects.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = registry[result["project_id"]]

    # This is exactly the doc's own step-0 dead-row test:
    # "indexed_at is null" OR "files_indexed is 0 and chunks_created is 0".
    is_dead_by_the_docs_own_rule = (
        entry.get("indexed_at") is None
        or (entry.get("files_indexed") == 0 and entry.get("chunks_created") == 0)
    )
    assert entry.get("indexed_at") is not None, (
        "sanity check on the doc's first dead-row clause: indexed_at is "
        "always set by _update_project_registry, so the doc's own "
        "'indexed_at is null' test can never actually fire for this state"
    )
    assert is_dead_by_the_docs_own_rule, (
        "a genuinely incomplete-but-resumable project (files_indexed=0, "
        "chunks_created=0, __incomplete__=True) reads as a dead row under the "
        "doc's own step-0 rule, which instructs a human to delete it"
    )


def test_abort_before_file_one_separates_nothing_to_do_from_nothing_indexed(
    isolated_indexing, tmp_path,
):
    """A pressure abort on the very first check, before a single file's hash is
    compared, against two projects that need completely different actions: one
    already fully indexed by a prior run, one never indexed at all.

    files_indexed, files_unchanged and chunks_created are all 0 either way,
    because they only count files this run actually looked at. So the response
    has to carry the difference somewhere, and the manifest has to keep it: a
    routine resync whose guard fires before it examines anything has confirmed
    nothing and changed nothing, and calling that complete index incomplete
    makes /search report a healthy project stale until some later run clears it.
    """
    indexing = isolated_indexing

    complete = _make_project(tmp_path / "complete", n_files=10)
    baseline = indexing.index_project(str(complete), StubEmbedder(), force=True)
    assert baseline["files_indexed"] == 10
    assert indexing.index_is_incomplete(str(complete)) is False

    never_indexed = _make_project(tmp_path / "fresh", n_files=10)

    def abort_immediately():
        return "free RAM 100 MB (need 4322 MB)"

    resync = indexing.index_project(
        str(complete), StubEmbedder(), force=False, should_abort=abort_immediately,
    )
    first_run = indexing.index_project(
        str(never_indexed), StubEmbedder(), force=False, should_abort=abort_immediately,
    )

    # Identical on every field that counts examined files, in both cases.
    for result in (resync, first_run):
        assert result["files_indexed"] == 0
        assert result["files_unchanged"] == 0
        assert result["chunks_created"] == 0
        assert result["files_pending"] == 10, (
            "a caller cannot tell an untouched run from a completed one without "
            "being told how many files went unexamined"
        )

    assert resync["index_incomplete"] is False, (
        "every one of the 10 files is already indexed and unchanged, so this "
        "run left a complete index complete and the caller has nothing to do"
    )
    assert indexing.index_is_incomplete(str(complete)) is False, (
        "a should_abort that fired before any file was hashed re-marked a "
        "previously complete project __incomplete__, which makes /search warn "
        "that a fully indexed project is stale"
    )

    assert first_run["index_incomplete"] is True, (
        "nothing is indexed here and 10 files still need doing, so this run "
        "must not read the same as the resync above"
    )
    assert indexing.index_is_incomplete(str(never_indexed)) is True


# ---------------------------------------------------------------------------
# POST /index-project, driven through the real handler with the real
# production defaults (INDEX_PRESSURE_CHECK_S=15, MIN_FREE_RAM_MB from config)
# rather than the interval_s=0 the rest of this file uses for speed.
#
# A checkpoint that lives for one request has to check the machine it was
# handed, not the machine it has 15 seconds from now: a run that finishes
# inside the interval would otherwise never be sampled, however starved the
# machine was for all of it, and "already below the floor before file 0" is
# precisely the incident the guard exists for.
# ---------------------------------------------------------------------------

class _StubRequest:
    """Enough of aiohttp's Request for handle_index_project: a JSON body."""

    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def test_manual_index_stops_before_file_one_when_ram_is_already_below_the_floor(
    isolated_indexing, tmp_path, monkeypatch,
):
    """The exact scenario in the ticket: free RAM already critically low
    (0.1 GB observed) when a manual /index-project arrives.

    Driven through handle_index_project rather than through a hand-built
    checkpoint, so it is the endpoint's own guard under test. StubEmbedder
    makes the run finish in well under INDEX_PRESSURE_CHECK_S, which is the
    window a per-request checkpoint used to spend entirely unguarded.
    """
    import server.app as app_mod
    from server.config import MIN_FREE_RAM_MB

    indexing = isolated_indexing
    project = _make_project(tmp_path / "proj", n_files=25)

    assert MIN_FREE_RAM_MB > 100, "test setup: 100 MB free has to be under the floor"

    # The lock and the model cache are the only server state the handler needs;
    # patching them keeps this off the real state/ directory.
    monkeypatch.setattr(app_mod, "acquire_index_lock", lambda *a, **kw: True)
    monkeypatch.setattr(app_mod, "release_index_lock", lambda *a, **kw: None)
    monkeypatch.setattr(app_mod, "_model_cache", StubEmbedder())

    # Available RAM pinned as low as the ticket's own 0.1 GB incident, for the
    # whole run. CPU is idle, so CPU can play no part in the outcome.
    starved = FakePsutil(cpu_sequence=[0.0] * 200, available_mb=100)

    with patch.dict(sys.modules, {"psutil": starved}):
        response = asyncio.run(app_mod.handle_index_project(
            _StubRequest({"project_path": str(project), "force": True})
        ))

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200, body

    assert body["files_indexed"] == 0, (
        f"{body['files_indexed']} of 25 files were embedded on a machine that "
        f"was under the free RAM floor before the request even arrived"
    )
    assert "free RAM 100 MB" in body["stopped_early"], body["stopped_early"]
    assert f"need {MIN_FREE_RAM_MB:.0f} MB" in body["stopped_early"], (
        f"the reason has to name the real numbers, got {body['stopped_early']!r}"
    )
    assert "CPU" not in body["stopped_early"], (
        f"the start check has no usable cpu_percent baseline yet, so it must "
        f"not make a CPU claim: {body['stopped_early']!r}"
    )
    assert body["files_pending"] == 25
    # A force run emptied the collection, so this really is incomplete, and the
    # next call with force off is what finishes it.
    assert body["index_incomplete"] is True
    assert indexing.index_is_incomplete(str(project)) is True


def test_manual_index_on_a_healthy_machine_finishes_and_samples_ram_once(
    isolated_indexing, tmp_path, monkeypatch,
):
    """The other half of the guard's contract: checking the machine at the start
    must not cost a healthy run anything. It finishes every file, reports no
    stopped_early, and the whole 25 file run reads free RAM exactly once,
    because the interval never elapses."""
    import server.app as app_mod

    project = _make_project(tmp_path / "proj", n_files=25)

    monkeypatch.setattr(app_mod, "acquire_index_lock", lambda *a, **kw: True)
    monkeypatch.setattr(app_mod, "release_index_lock", lambda *a, **kw: None)
    monkeypatch.setattr(app_mod, "_model_cache", StubEmbedder())

    healthy = FakePsutil(cpu_sequence=[0.0] * 200, available_mb=8000)

    with patch.dict(sys.modules, {"psutil": healthy}):
        response = asyncio.run(app_mod.handle_index_project(
            _StubRequest({"project_path": str(project), "force": True})
        ))

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200, body
    assert body["files_indexed"] == 25, body
    assert body["chunks_created"] > 0, "test setup: nothing was actually indexed"
    assert "stopped_early" not in body, (
        f"a healthy machine had a manual index run stop early: "
        f"{body.get('stopped_early')!r}"
    )
    assert healthy.vm_calls == 1, (
        f"{healthy.vm_calls} psutil memory reads across 25 files -- the probe "
        f"is meant to cost one read at the start and then one per "
        f"INDEX_PRESSURE_CHECK_S, not one per file"
    )


def test_request_scoped_checkpoint_checks_ram_at_once_then_throttles_as_before():
    """The mechanism the endpoint test rests on, shown directly: the first call
    to a request scoped checkpoint samples free RAM immediately, and every call
    after it is throttled by the interval exactly as before."""
    from server.resource_guard import PressureCheckpoint

    critically_low = FakePsutil(cpu_sequence=[0.0, 0.0, 0.0], available_mb=100)  # 0.1 GB
    with patch.dict(sys.modules, {"psutil": critically_low}):
        checkpoint = PressureCheckpoint(check_ram_at_start=True)  # else defaults
        first = checkpoint.pressure()
        second = checkpoint.pressure()

    assert first is not None and "free RAM" in first, (
        f"a run starting at 100 MB free was told to carry on: {first!r} -- the "
        f"15s interval must not swallow the first check on a checkpoint that "
        f"only lives as long as one request"
    )
    assert second is None, (
        f"the start check is a one off; the interval has to throttle "
        f"everything after it, got {second!r}"
    )


def test_start_check_ignores_cpu_because_it_has_no_baseline_to_diff_against():
    """cpu_percent(interval=None) reports the delta since the previous call, and
    the previous call here is the priming one microseconds earlier. psutil
    documents anything under 0.1s as unreliable, so a CPU throttle configured
    below 100 must not be able to abort a run on that reading. Free RAM is an
    instantaneous level and carries no such caveat, which is why it is the half
    the start check uses."""
    from server.resource_guard import PressureCheckpoint

    # Healthy RAM, and a cpu_percent that would trip an 80% ceiling instantly.
    hostile_cpu = FakePsutil(cpu_sequence=[99.0] * 5, available_mb=8000)
    with patch.dict(sys.modules, {"psutil": hostile_cpu}):
        cp = PressureCheckpoint(
            interval_s=3600, max_percent=80, min_free_ram_mb=3072,
            check_ram_at_start=True,
        )
        assert cp.pressure() is None, (
            "the start check aborted a healthy run on a sub millisecond CPU "
            "delta, which is the reading psutil says not to trust"
        )
    assert hostile_cpu.vm_calls == 1, (
        f"the start check has to read free RAM exactly once, got "
        f"{hostile_cpu.vm_calls} reads"
    )


class _FakeClock:
    """Stands in for resource_guard's `time` module, so a test can cross an
    interval without sleeping through it."""

    def __init__(self, now=1000.0):
        self.now = now

    def monotonic(self):
        return self.now


def test_a_slow_start_does_not_buy_the_run_another_interval_of_silence(monkeypatch):
    """Loading an embedding model can take longer than the whole interval, so
    the first check often arrives already past due. The start check must not
    push the first full sample out by another interval from there: by then the
    machine has gone a full interval unsampled, which is what the interval was
    supposed to bound."""
    from server import resource_guard

    clock = _FakeClock()
    monkeypatch.setattr(resource_guard, "time", clock)

    fake = FakePsutil(cpu_sequence=[0.0, 95.0, 95.0], available_mb=8000)
    with patch.dict(sys.modules, {"psutil": fake}):
        cp = resource_guard.PressureCheckpoint(
            interval_s=15, max_percent=80, min_free_ram_mb=3072,
            check_ram_at_start=True,
        )
        clock.now += 40  # a slow model load, well past one interval

        assert cp.pressure() is None, "the start check: free RAM is healthy"
        assert "CPU 95%" in cp.pressure(), (
            "the interval elapsed during startup, so the next check had to be a "
            "real sample rather than another 15 seconds of silence"
        )


def test_default_checkpoint_takes_no_sample_at_all_before_its_first_interval():
    """The sweep (auto_reindex._sweep_project) and cli/reindex_batch.py build
    PressureCheckpoint() with no overrides and reuse one instance across every
    project in a pass, having already gated on wait_for_system_headroom()
    before starting. Their sampling rate must not change: no psutil read of
    any kind before the first interval elapses."""
    from server.resource_guard import PressureCheckpoint

    fake = FakePsutil(cpu_sequence=[0.0] * 10, available_mb=100)
    with patch.dict(sys.modules, {"psutil": fake}):
        cp = PressureCheckpoint(interval_s=3600, max_percent=80, min_free_ram_mb=3072)
        cpu_calls_after_priming = fake._calls
        for _ in range(200):
            assert cp.pressure() is None

    assert fake._calls == cpu_calls_after_priming, (
        f"{fake._calls - cpu_calls_after_priming} cpu_percent reads in 200 calls"
    )
    assert fake.vm_calls == 0, (
        f"{fake.vm_calls} virtual_memory reads before the first interval -- a "
        f"long lived checkpoint now samples more often than it used to"
    )


# ---------------------------------------------------------------------------
# PressureCheckpoint: the synchronous probe the worker thread uses
# ---------------------------------------------------------------------------

def test_checkpoint_reports_pressure_and_stays_quiet_when_idle():
    from server.resource_guard import PressureCheckpoint

    busy = FakePsutil(cpu_sequence=[95.0] * 5, available_mb=8000)
    idle = FakePsutil(cpu_sequence=[5.0] * 5, available_mb=8000)

    with patch.dict(sys.modules, {"psutil": busy}):
        cp = PressureCheckpoint(interval_s=0, max_percent=80, min_free_ram_mb=3072)
        assert "CPU 95%" in cp.pressure()

    with patch.dict(sys.modules, {"psutil": idle}):
        cp = PressureCheckpoint(interval_s=0, max_percent=80, min_free_ram_mb=3072)
        assert cp.pressure() is None


def test_checkpoint_throttles_so_the_probe_is_not_its_own_cpu_cost():
    """Called per file on a 4000-file project, an unthrottled probe would be
    thousands of psutil samples. Only one per interval may reach psutil."""
    from server.resource_guard import PressureCheckpoint

    fake = FakePsutil(cpu_sequence=[95.0] * 100, available_mb=8000)
    with patch.dict(sys.modules, {"psutil": fake}):
        cp = PressureCheckpoint(interval_s=3600, max_percent=80, min_free_ram_mb=3072)
        calls_after_priming = fake._calls
        for _ in range(500):
            assert cp.pressure() is None
        assert fake._calls == calls_after_priming, (
            f"{fake._calls - calls_after_priming} psutil samples in 500 calls "
            f"-- the interval throttle is not working"
        )


def test_checkpoint_degrades_to_no_pressure_when_psutil_missing():
    """Requirement 6 again, on the new code path: a missing optional
    dependency must not stop reindexing dead."""
    from server.resource_guard import PressureCheckpoint

    real_import = __import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *a, **kw)

    with patch("builtins.__import__", side_effect=fake_import):
        cp = PressureCheckpoint(interval_s=0, max_percent=80, min_free_ram_mb=3072)
        assert cp.pressure() is None


@pytest.mark.asyncio
async def test_mutant_remove_finally_leaves_flag_stuck(auto_reindex, monkeypatch, tmp_path):
    """Mutant 3, run for real: patch out the effect of the `finally` (by
    forcing an exception path that skips it) and show the flag gets stuck,
    then show the real code (with the finally) does not."""
    registry_path = tmp_path / "projects.json"
    registry_path.write_text(json.dumps({"p1": {"project_path": str(tmp_path)}}))
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)

    async def headroom_true(*a, **kw):
        return True

    async def raising_sweep(pid, entry, model_cache):
        raise RuntimeError("boom")

    monkeypatch.setattr(auto_reindex, "wait_for_cpu_headroom", headroom_true)
    monkeypatch.setattr(auto_reindex, "_sweep_project", raising_sweep)
    monkeypatch.setattr(auto_reindex, "_release_project_resources", lambda pid: None)

    calls = {"n": 0}

    async def sleep_then_cancel(_s):
        calls["n"] += 1
        if calls["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(auto_reindex, "asyncio", _FakeAsyncioNamespace(asyncio, sleep_then_cancel))

    with pytest.raises(asyncio.CancelledError):
        await auto_reindex.auto_reindex_loop(lambda: object())

    # RuntimeError from _sweep_project is caught by the per-project except
    # Exception handler (real code), so the real `finally` still runs and
    # this must be False. If the `finally` were removed (mutant 3) and an
    # *uncaught* exception path existed, this would be left True.
    assert auto_reindex._sweep_in_progress is False


# ---------------------------------------------------------------------------
# _apply_torch_thread_cap
# ---------------------------------------------------------------------------

def test_torch_thread_cap_actually_calls_set_num_threads():
    from server import embedding
    embedding._thread_cap_applied = False
    calls = {"threads": None, "interop": None}

    fake_torch = MagicMock()
    fake_torch.set_num_threads.side_effect = lambda n: calls.__setitem__("threads", n)
    fake_torch.set_num_interop_threads.side_effect = lambda n: calls.__setitem__("interop", n)

    with patch.dict(sys.modules, {"torch": fake_torch}):
        embedding._apply_torch_thread_cap()

    assert calls["threads"] is not None, "set_num_threads was never called"
    from server.config import TORCH_THREADS
    assert calls["threads"] == TORCH_THREADS


def test_torch_thread_cap_survives_interop_runtimeerror():
    """set_num_interop_threads raises RuntimeError once parallel work has
    started. Confirm that doesn't take the intra-op cap down with it."""
    from server import embedding
    embedding._thread_cap_applied = False

    fake_torch = MagicMock()
    applied = {"threads": None}
    fake_torch.set_num_threads.side_effect = lambda n: applied.__setitem__("threads", n)
    fake_torch.set_num_interop_threads.side_effect = RuntimeError("already started")

    with patch.dict(sys.modules, {"torch": fake_torch}):
        embedding._apply_torch_thread_cap()  # must not raise

    assert applied["threads"] is not None


def test_torch_thread_cap_only_applies_once():
    from server import embedding
    embedding._thread_cap_applied = False
    fake_torch = MagicMock()

    with patch.dict(sys.modules, {"torch": fake_torch}):
        embedding._apply_torch_thread_cap()
        embedding._apply_torch_thread_cap()
        embedding._apply_torch_thread_cap()

    assert fake_torch.set_num_threads.call_count == 1


# ---------------------------------------------------------------------------
# _release_project_resources: does the path it builds actually match the
# path ChromaStore was opened with?
# ---------------------------------------------------------------------------

def test_release_project_resources_evicts_the_real_connection(tmp_path, monkeypatch):
    from server import auto_reindex
    from server.store import ChromaStore, Chunk

    fake_databases_dir = tmp_path / "databases"
    pid = "abc123"
    chroma_dir = fake_databases_dir / "_projects" / pid / "chroma"
    chroma_dir.mkdir(parents=True)

    store = ChromaStore(persist_dir=str(chroma_dir))
    store.create_collection("codebase")
    store.add_chunks("codebase", [
        Chunk(id="c1", content="hello world", embedding=[0.1, 0.2, 0.3], metadata={}),
    ])
    db_path = store._db_path
    from server.store import _conn_cache
    assert db_path in _conn_cache, "connection was never cached in the first place"

    # Checked in first, so this is the sweep's normal case: nothing holds the
    # handle, so the eviction closes and drops the record on the spot. A record
    # still held is deferred instead and deliberately stays cached, which would
    # make the assertion below pass or fail for a reason that has nothing to do
    # with the path this builds.
    store.close()

    import server.config as config_mod
    monkeypatch.setattr(config_mod, "DATABASES_DIR", fake_databases_dir)

    auto_reindex._release_project_resources(pid)

    assert db_path not in _conn_cache, (
        "evict_cache did not remove the connection -- the path "
        "_release_project_resources built does not match the real cache key"
    )


def test_mutant_missing_chroma_suffix_is_a_noop(tmp_path, monkeypatch):
    """Mutant 6: build a path missing the /chroma suffix. Prove this makes
    the release a silent no-op that looks like it succeeded."""
    from server.store import ChromaStore, Chunk

    fake_databases_dir = tmp_path / "databases"
    pid = "abc123"
    chroma_dir = fake_databases_dir / "_projects" / pid / "chroma"
    chroma_dir.mkdir(parents=True)

    store = ChromaStore(persist_dir=str(chroma_dir))
    store.create_collection("codebase")
    store.add_chunks("codebase", [
        Chunk(id="c1", content="hi", embedding=[0.1, 0.2], metadata={}),
    ])
    db_path = store._db_path
    from server.store import _conn_cache
    assert db_path in _conn_cache

    # Checked in first, so a hit on the right path would drop the record here and
    # now. Left held, the record stays cached either way and the assertion below
    # could no longer tell a miss from a hit.
    store.close()

    # The mutant: omit "/chroma".
    wrong_path = fake_databases_dir / "_projects" / pid
    ChromaStore.evict_cache(str(wrong_path))

    assert db_path in _conn_cache, "mutant test setup is wrong: eviction should have missed"
    # cleanup
    ChromaStore.evict_cache(str(chroma_dir))


# ---------------------------------------------------------------------------
# _sweep_project's bool return and the release that is gated on it in
# auto_reindex_loop: this is the actual production incident (a running
# /index-project killed by "Cannot operate on a closed database" because the
# sweep released a project's connection unconditionally, even when it had
# never touched that project this pass).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_release_is_skipped_when_the_index_lock_was_busy(auto_reindex, monkeypatch, tmp_path):
    """The exact production incident: _sweep_project bails with the index
    lock held by another job (a real /index-project already running), and
    the sweep loop must NOT evict that project's connection out from under
    the job that is still using it.

    This is the mutant-1 kill test: revert the caller to an unconditional
    `_release_project_resources(project.pid)` and this fails, because the
    release would then run even though _sweep_project returned False for
    exactly the reason (lock busy) the original bug hit.
    """
    # _read_registry is stubbed directly rather than pointing STATE_DIR at
    # tmp_path: auto_reindex._read_registry is bound at import time to
    # reindex_unit.read_registry, which reads reindex_unit's own STATE_DIR
    # global, not auto_reindex's. Patching auto_reindex.STATE_DIR (the
    # pattern several tests in this file use) has no effect on what the loop
    # actually reads; it silently falls through to this machine's real
    # state/projects.json instead of the fixture below. Confirmed directly:
    # patching only STATE_DIR here made the loop sweep this machine's real
    # registered projects, not the single "p1" fixture project.
    monkeypatch.setattr(
        auto_reindex, "_read_registry",
        lambda: {"p1": {"project_path": str(tmp_path)}},
    )

    # Real _sweep_project, not a stub: force it down the "lock busy" branch.
    monkeypatch.setattr(auto_reindex, "find_changed_files",
                        lambda p: (["f1.py"], []))
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **kw: False)

    released = []
    monkeypatch.setattr(auto_reindex, "_release_project_resources",
                        lambda pid: released.append(pid))

    async def headroom_true(*a, **kw):
        return True

    # Both the outer gate that runs before the loop (wait_for_cpu_headroom, an
    # alias) and the per project gate (wait_for_system_headroom, called
    # directly inside the for loop) must be stubbed. Leaving the real one in
    # place means its own internal `await asyncio.sleep(0.1)` shares the call
    # counter below with the outer `await asyncio.sleep(INTERVAL_S)` and
    # fires the CancelledError before _sweep_project is ever reached, which
    # would make this test pass for the wrong reason, never getting there at
    # all.
    monkeypatch.setattr(auto_reindex, "wait_for_cpu_headroom", headroom_true)
    monkeypatch.setattr(auto_reindex, "wait_for_system_headroom", headroom_true)

    calls = {"n": 0}

    async def sleep_then_cancel(_s):
        calls["n"] += 1
        if calls["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(auto_reindex, "asyncio", _FakeAsyncioNamespace(asyncio, sleep_then_cancel))

    with pytest.raises(asyncio.CancelledError):
        await auto_reindex.auto_reindex_loop(lambda: object())

    assert released == [], (
        f"_release_project_resources was called for {released} even though "
        f"_sweep_project bailed on a busy index lock -- this is the exact "
        f"incident that closed a shared connection under a running index job"
    )


@pytest.mark.asyncio
async def test_release_runs_when_the_sweep_actually_did_work(auto_reindex, monkeypatch, tmp_path):
    """The other half: gating the release on a busy lock must not silently
    turn into never releasing at all, which would leak one open sqlite
    handle per project for the life of the process (the exact cost the
    comment above _release_project_resources's call site describes)."""
    # See the comment in the sibling test above: _read_registry has to be
    # stubbed directly, not reached via STATE_DIR.
    monkeypatch.setattr(
        auto_reindex, "_read_registry",
        lambda: {"p1": {"project_path": str(tmp_path)}},
    )

    monkeypatch.setattr(auto_reindex, "find_changed_files", lambda p: ([], []))

    async def fake_sweep_project(pid, entry, model_cache, checkpoint=None):
        return True  # actually did work and released the lock itself

    monkeypatch.setattr(auto_reindex, "_sweep_project", fake_sweep_project)

    released = []
    monkeypatch.setattr(auto_reindex, "_release_project_resources",
                        lambda pid: released.append(pid))

    async def headroom_true(*a, **kw):
        return True

    # See the comment in the sibling test above: both names have to be
    # stubbed or the real wait_for_system_headroom eats the fake sleep's
    # call budget before _sweep_project is ever reached.
    monkeypatch.setattr(auto_reindex, "wait_for_cpu_headroom", headroom_true)
    monkeypatch.setattr(auto_reindex, "wait_for_system_headroom", headroom_true)

    calls = {"n": 0}

    async def sleep_then_cancel(_s):
        calls["n"] += 1
        if calls["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(auto_reindex, "asyncio", _FakeAsyncioNamespace(asyncio, sleep_then_cancel))

    with pytest.raises(asyncio.CancelledError):
        await auto_reindex.auto_reindex_loop(lambda: object())

    assert released == ["p1"], (
        "a sweep that actually proceeded must still release its handles, or "
        "every registered project leaks one open sqlite connection forever"
    )


def test_sweep_project_returns_false_specifically_for_a_busy_lock(auto_reindex, monkeypatch, tmp_path):
    """Mutant-2 kill test: invert `if not acquire_index_lock():` to
    `if acquire_index_lock():` in _sweep_project. Under that mutant, a busy
    lock (acquire returns False) makes the condition False, so the body
    that assumes the lock was acquired runs anyway -- corrupting a project
    another job holds the lock for -- and this test's return-value
    assertion fails because the busy-lock path would then fall through to
    `return True` instead of `return False`.
    """
    import asyncio as real_asyncio

    monkeypatch.setattr(auto_reindex, "find_changed_files", lambda p: (["f1.py"], []))
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **kw: False)

    result = real_asyncio.run(
        auto_reindex._sweep_project("p1", {"project_path": str(tmp_path)}, object())
    )
    assert result is False, (
        "_sweep_project must return False when the index lock is busy, not "
        "True -- a True here tells the caller it is safe to evict the "
        "connection a still-running job is using"
    )


def test_release_index_lock_only_clears_its_own_pid(tmp_path, monkeypatch):
    """Mutant-3 kill test: drop the `lock_data.get('pid') == os.getpid()`
    check in release_index_lock(). Under that mutant this test fails,
    because release_index_lock() would delete a lock file recorded under a
    DIFFERENT live PID -- letting this process's finally-block cleanup tear
    down another process's in-flight index lock and letting a second sweep
    or a manual /index-project start concurrently with the first.
    """
    from server import indexing

    monkeypatch.setattr(indexing, "_INDEX_LOCK_PATH", tmp_path / "index-lock.json")
    other_pid = indexing.os.getpid() + 1  # guaranteed different from ours
    indexing._INDEX_LOCK_PATH.write_text(json.dumps({
        "pid": other_pid, "operation": "index", "started": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")

    indexing.release_index_lock()

    assert indexing._INDEX_LOCK_PATH.exists(), (
        "release_index_lock() deleted a lock file recorded under a "
        "different, still-running PID -- this would let two indexing "
        "operations run concurrently against the same sqlite connection"
    )


def test_lock_is_still_released_on_the_new_full_reindex_return_true_path(
    tmp_path, monkeypatch, auto_reindex,
):
    """The added `return True` in the full-reindex branch sits inside the
    same `try:` the `finally: release_index_lock()` already covered. Confirm
    that path still actually releases the lock -- a `return` inside a `try`
    always runs the `finally` in real Python, but this is exactly the kind
    of control-flow change (SIR: statement removal / reordering) that a
    careless refactor gets wrong, so it is asserted here against the real
    function rather than trusted from reading it.
    """
    monkeypatch.setattr(auto_reindex, "STATE_DIR", tmp_path)
    monkeypatch.setattr(auto_reindex, "find_changed_files",
                        lambda p: ([f"f{i}.py" for i in range(60)], []))  # >= FULL_REINDEX_THRESHOLD
    monkeypatch.setattr(auto_reindex, "acquire_index_lock", lambda *a, **kw: True)
    monkeypatch.setattr(auto_reindex, "index_is_incomplete", lambda p: False)
    monkeypatch.setattr(
        auto_reindex, "index_project",
        lambda *a, **kw: {"files_indexed": 60, "chunks_created": 60, "files_failed": 0},
    )

    released = {"n": 0}
    monkeypatch.setattr(auto_reindex, "release_index_lock",
                        lambda: released.__setitem__("n", released["n"] + 1))

    import asyncio as real_asyncio
    result = real_asyncio.run(
        auto_reindex._sweep_project("p1", {"project_path": str(tmp_path)}, object())
    )

    assert result is True
    assert released["n"] == 1, (
        "the full-reindex branch's new `return True` skipped the `finally` "
        "and never released the index lock -- every subsequent sweep or "
        "manual /index-project would see the lock as permanently busy"
    )


@pytest.mark.asyncio
async def test_swept_counter_excludes_projects_that_never_actually_swept(
    auto_reindex, monkeypatch, tmp_path, caplog,
):
    """The "Reindex sweep done: %d project(s)" line must count projects this
    pass really touched.

    `swept += 1` used to run regardless of `proceeded`, so a pass where every
    project bailed on a busy index lock still reported one project per registered
    project. Nothing downstream branches on the number, so this is log accuracy
    only, and log accuracy is the whole reason to read that line: it is the one
    place lock contention shows up.
    """
    # _read_registry is stubbed directly rather than pointing STATE_DIR at
    # tmp_path: it is bound at import time to reindex_unit.read_registry, which
    # reads reindex_unit's own STATE_DIR global. Patching auto_reindex.STATE_DIR
    # does not reach it, and the loop then falls through to this machine's real
    # state/projects.json instead of the fixture below.
    monkeypatch.setattr(
        auto_reindex, "_read_registry",
        lambda: {"p1": {"project_path": str(tmp_path)}},
    )

    async def fake_sweep_project(pid, entry, model_cache, checkpoint=None):
        return False  # bailed on a busy lock, touched nothing

    monkeypatch.setattr(auto_reindex, "_sweep_project", fake_sweep_project)
    monkeypatch.setattr(auto_reindex, "_release_project_resources", lambda pid: None)

    async def headroom_true(*a, **kw):
        return True

    monkeypatch.setattr(auto_reindex, "wait_for_cpu_headroom", headroom_true)
    monkeypatch.setattr(auto_reindex, "wait_for_system_headroom", headroom_true)

    calls = {"n": 0}

    async def sleep_then_cancel(_s):
        calls["n"] += 1
        if calls["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(auto_reindex, "asyncio", _FakeAsyncioNamespace(asyncio, sleep_then_cancel))

    with caplog.at_level("INFO", logger="server.auto_reindex"):
        with pytest.raises(asyncio.CancelledError):
            await auto_reindex.auto_reindex_loop(lambda: object())

    done_lines = [r.message for r in caplog.records if "Reindex sweep done" in r.message]
    assert done_lines, "the sweep-done summary line was never logged"
    assert "0 project(s)" in done_lines[-1], (
        f"a pass where every project bailed on a busy index lock reported real "
        f"work: {done_lines[-1]!r}"
    )


# ---------------------------------------------------------------------------
# server_ctl.py: stop marker / restart ordering
# ---------------------------------------------------------------------------

def test_stop_without_pid_file_still_writes_marker(tmp_path, server_ctl, monkeypatch):
    """Mutant 5 kill test: cmd_stop must mark stopped even when there is no
    PID file (a server started by hand, or one that already died)."""
    monkeypatch.setattr(server_ctl, "_state_dir", lambda: tmp_path)
    assert server_ctl.cmd_stop(type("A", (), {})()) == 0
    assert (tmp_path / server_ctl.STOP_MARKER_NAME).exists()


def test_restart_clears_marker_after_writing_it(tmp_path, server_ctl, monkeypatch):
    """cmd_restart = cmd_stop then cmd_start. Confirm start really does clear
    the marker stop just wrote. That is intended: restart is only ever run by
    hand from the CLI."""
    monkeypatch.setattr(server_ctl, "_state_dir", lambda: tmp_path)
    monkeypatch.setattr(server_ctl, "_port", lambda: 65432)
    monkeypatch.setattr(server_ctl, "_port_in_use", lambda port: True)  # skip actually spawning
    ns = type("A", (), {})()
    server_ctl.cmd_restart(ns)
    assert not (tmp_path / server_ctl.STOP_MARKER_NAME).exists()


def test_marker_write_failure_is_reported_not_reported_as_success(tmp_path, server_ctl, monkeypatch, capsys):
    """Attack: state/ is unwritable when the user runs stop.

    The marker's absence is what makes the next prompt resurrect the server, so
    a stop that could not record itself must not read as a successful stop.
    cmd_stop has to say so unmistakably and exit non-zero, instead of printing
    "Server stopped." over a marker that does not exist.
    """
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(server_ctl, "_state_dir", lambda: state)

    def boom_mkdir(*a, **kw):
        raise OSError("state/ is read-only in this scenario")

    monkeypatch.setattr(Path, "mkdir", boom_mkdir)
    try:
        persisted = server_ctl._mark_stopped_by_user(state)
        exit_code = server_ctl.cmd_stop(type("A", (), {})())
    finally:
        monkeypatch.undo()

    marker = state / server_ctl.STOP_MARKER_NAME
    assert not marker.exists(), "sanity: the marker really didn't get written"
    assert persisted is False, (
        "_mark_stopped_by_user reported success for a marker that is not there"
    )
    assert exit_code != 0, (
        "cmd_stop exited 0 with no stop marker on disk -- a script cannot tell "
        "that the stop will be undone by the next prompt"
    )

    err = capsys.readouterr().err
    assert "ERROR" in err and "NOT recorded" in err, (
        f"the failure has to be unmistakable on stderr, got: {err!r}"
    )


def test_stop_with_a_live_pid_file_also_exits_nonzero_when_the_marker_fails(
    tmp_path, server_ctl, monkeypatch, capsys
):
    """The same durability failure down the other branch of cmd_stop, the one
    that actually kills a process and prints "Server stopped.". Killing the
    server and then not recording it is precisely the incident: the next prompt
    finds it down, finds no marker, and brings it back."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "server.json").write_text(json.dumps({"pid": 424242, "port": 65432}))
    monkeypatch.setattr(server_ctl, "_state_dir", lambda: state)
    monkeypatch.setattr(server_ctl, "_is_process_alive", lambda pid: False)

    real_write_text = Path.write_text

    def selective_write(self, *a, **kw):
        if self.name == server_ctl.STOP_MARKER_NAME:
            raise OSError("no space left on device")
        return real_write_text(self, *a, **kw)

    monkeypatch.setattr(Path, "write_text", selective_write)
    exit_code = server_ctl.cmd_stop(type("A", (), {})())
    monkeypatch.undo()

    assert exit_code != 0, (
        "cmd_stop killed the server, failed to record the stop, and still "
        "exited 0"
    )
    out = capsys.readouterr()
    assert "Server stopped." not in out.out, (
        f"printed plain success over a stop that did not persist: {out.out!r}"
    )
    assert "NOT recorded" in out.err


def test_marker_that_does_not_survive_the_write_is_caught(tmp_path, server_ctl, monkeypatch):
    """The nastier version: the write itself raises nothing, but nothing lands
    (a full disk that swallows the write, a synced folder, an antivirus
    quarantine). Durability is the whole point of this file, so a read back is
    the only thing that actually proves it."""
    state = tmp_path / "state"
    state.mkdir()

    monkeypatch.setattr(Path, "write_text", lambda self, *a, **kw: len(a[0]) if a else 0)

    assert server_ctl._mark_stopped_by_user(state) is False, (
        "write_text reported success but wrote nothing, and "
        "_mark_stopped_by_user believed it"
    )
