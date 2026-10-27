"""The auto reindex sweep must never evict a model at a group boundary.

server/auto_reindex.py:auto_reindex_loop groups projects by embedding model
(server/reindex_unit.py:plan_sweep). It used to call model_cache.evict_all()
whenever the model changed between consecutive projects, first unconditionally
and later gated on whether the finishing group had done real work. Both
versions are gone, and the reason is measured rather than stylistic.

torch does not return CPU allocator arenas to the OS. Every evict and reload
cycle therefore left roughly 1.7 GB behind permanently, by this project's own
measurement recorded on ModelCache.evict_all. The sweep ran six of those cycles
an hour, and the server process reached 18.8 GB RSS on a 32 GB machine with
free RAM at 0 MB. There is no in process remedy on Windows: malloc_trim is a
glibc export, and Microsoft documents HeapCompact as reporting the largest free
block without compacting further.

Residency was never the sweep's job to bound anyway. ModelCache._enforce_max_
resident caps it at DEFAULT_MAX_RESIDENT on every single load, which is why the
removed call described itself as a release sooner optimisation rather than a
safety net. Removing it means the cap evicts strictly less often.

These tests drive the real auto_reindex_loop coroutine end to end, with the
registry, the plan, the per project sweep and the model cache all faked, so the
assertions are about the loop's own control flow rather than a reimplementation
of it. The last two prove the removal is a real behaviour change and that the
cap it relies on actually holds.
"""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))

from server import auto_reindex  # noqa: E402
from server.reindex_unit import PlannedProject  # noqa: E402


class _StopSweep(Exception):
    """Raised from the second `_read_registry()` call to end the `while True`
    loop after exactly the sweep(s) a test cares about, without needing a
    timeout or a cancellation race."""


@pytest.fixture()
def reset_auto_reindex():
    auto_reindex._sweep_in_progress = False
    auto_reindex._sweep_started_at = 0.0
    yield
    auto_reindex._sweep_in_progress = False
    auto_reindex._sweep_started_at = 0.0


def _wire_common(monkeypatch, planned_sequence, registry_sequence):
    """Patch everything auto_reindex_loop touches except the model cache.

    planned_sequence: list of `list[PlannedProject]`, one per real sweep.
    registry_sequence: list of truthy dict stand-ins, one per real sweep.
    After both are exhausted, the next `_read_registry()` call raises
    `_StopSweep` so the infinite loop ends deterministically.
    """
    monkeypatch.setattr(auto_reindex, "INTERVAL_S", 0)
    monkeypatch.setattr(
        auto_reindex, "wait_for_cpu_headroom", AsyncMock(return_value=True)
    )

    registry_calls = list(registry_sequence)

    def _next_registry():
        if registry_calls:
            return registry_calls.pop(0)
        raise _StopSweep()

    monkeypatch.setattr(auto_reindex, "_read_registry", _next_registry)

    planned_calls = list(planned_sequence)
    monkeypatch.setattr(
        auto_reindex, "plan_sweep", MagicMock(side_effect=lambda *_a, **_k: planned_calls.pop(0))
    )
    monkeypatch.setattr(auto_reindex, "_release_project_resources", MagicMock())


async def _run_sweeps(monkeypatch, planned_sequence, proceeded_map, exception_map=None,
                       headroom_side_effect=None):
    """Drive auto_reindex_loop through len(planned_sequence) real sweeps and
    stop. Returns (evict_all mock, call_log of pids handed to _sweep_project).
    """
    exception_map = exception_map or {}
    _wire_common(monkeypatch, planned_sequence, [{"__nonempty__": True}] * len(planned_sequence))

    if headroom_side_effect is None:
        monkeypatch.setattr(
            auto_reindex, "wait_for_system_headroom", AsyncMock(return_value=True)
        )
    else:
        monkeypatch.setattr(
            auto_reindex, "wait_for_system_headroom",
            AsyncMock(side_effect=headroom_side_effect),
        )

    call_log = []

    async def fake_sweep_project(pid, entry, model_cache):
        call_log.append(pid)
        if pid in exception_map:
            raise exception_map[pid]
        return proceeded_map.get(pid, False)

    monkeypatch.setattr(auto_reindex, "_sweep_project", AsyncMock(side_effect=fake_sweep_project))

    model_cache = MagicMock()
    model_cache.evict_all = MagicMock()

    with pytest.raises(_StopSweep):
        await auto_reindex.auto_reindex_loop(lambda: model_cache)

    return model_cache.evict_all, call_log


# ---------------------------------------------------------------------------
# The core contract, stated six ways because the removed code had six
# different paths that could reach an eviction.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_every_group_does_real_work_and_nothing_is_ever_evicted(
    monkeypatch, reset_auto_reindex,
):
    """The case the old gate deliberately evicted on, and the one that drove
    RSS to 18 GB. Three model groups, every project doing real work, two
    boundaries crossed. Under the previous rule this evicted twice."""
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelA", 1),
        PlannedProject("p3", "/p3", "modelB", 1),
        PlannedProject("p4", "/p4", "modelB", 1),
        PlannedProject("p5", "/p5", "modelC", 1),
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned],
        proceeded_map={"p1": True, "p2": True, "p3": True, "p4": True, "p5": True},
    )
    assert call_log == ["p1", "p2", "p3", "p4", "p5"], "sweep did not visit every project"
    evict_all.assert_not_called()


@pytest.mark.asyncio
async def test_all_skipped_across_several_group_boundaries_never_evicts(
    monkeypatch, reset_auto_reindex,
):
    """A manual /index-project holds the lock, every project returns False,
    several model group boundaries are crossed."""
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelA", 1),
        PlannedProject("p3", "/p3", "modelB", 1),
        PlannedProject("p4", "/p4", "modelB", 1),
        PlannedProject("p5", "/p5", "modelC", 1),
    ]
    evict_all, call_log = await _run_sweeps(monkeypatch, [planned], proceeded_map={})

    assert call_log == ["p1", "p2", "p3", "p4", "p5"], "sweep did not visit every project"
    evict_all.assert_not_called()


@pytest.mark.asyncio
async def test_mixed_work_and_skips_never_evicts(monkeypatch, reset_auto_reindex):
    """An earlier project in a group works and the last one before the
    boundary skips. The old accumulator existed precisely to evict here."""
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelA", 1),
        PlannedProject("p3", "/p3", "modelB", 1),
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned], proceeded_map={"p1": True, "p2": False},
    )
    assert call_log == ["p1", "p2", "p3"]
    evict_all.assert_not_called()


@pytest.mark.asyncio
async def test_singleton_groups_never_evict(monkeypatch, reset_auto_reindex):
    """One project per model, so every step is a boundary. The worst case for
    the old rule, since a sweep of 14 projects across 3 models crosses a
    boundary on most iterations."""
    planned = [
        PlannedProject("p1", "/p1", "m1", 1),
        PlannedProject("p2", "/p2", "m2", 1),
        PlannedProject("p3", "/p3", "m3", 1),
    ]
    evict_all, _ = await _run_sweeps(
        monkeypatch, [planned], proceeded_map={"p1": True, "p2": False, "p3": True},
    )
    evict_all.assert_not_called()


@pytest.mark.asyncio
async def test_work_does_not_leak_into_the_next_sweep(monkeypatch, reset_auto_reindex):
    """Two consecutive sweeps, work in the first one, boundary in the second.
    Nothing carried across a sweep may reintroduce an eviction."""
    sweep1 = [PlannedProject("s1p1", "/s1p1", "modelA", 1)]
    sweep2 = [
        PlannedProject("s2p1", "/s2p1", "modelA", 1),
        PlannedProject("s2p2", "/s2p2", "modelB", 1),
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [sweep1, sweep2],
        proceeded_map={"s1p1": True, "s2p1": True},
    )
    assert call_log == ["s1p1", "s2p1", "s2p2"]
    evict_all.assert_not_called()


# ---------------------------------------------------------------------------
# Loop integrity. Removing the eviction must not have disturbed the paths that
# shared its enclosing block, and the removed accumulator was assigned inside
# the same `try` as `proceeded`.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_on_one_project_does_not_kill_the_rest_of_the_sweep(
    monkeypatch, reset_auto_reindex,
):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelA", 1),
        PlannedProject("p3", "/p3", "modelB", 1),
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned],
        proceeded_map={"p2": True},
        exception_map={"p1": RuntimeError("boom")},
    )
    assert call_log == ["p1", "p2", "p3"], (
        "an exception on p1 must not stop the loop from reaching p2 and p3. A "
        "reference to a name deleted alongside the eviction would raise "
        "UnboundLocalError or NameError and truncate here"
    )
    evict_all.assert_not_called()


@pytest.mark.asyncio
async def test_break_on_pressure_stops_the_sweep_early(monkeypatch, reset_auto_reindex):
    """Headroom fails as p3 is about to be considered, so the sweep abandons
    the rest. The projects already visited must stand."""
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelA", 1),
        PlannedProject("p3", "/p3", "modelB", 1),
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned],
        proceeded_map={"p1": True, "p2": True},
        headroom_side_effect=[True, True, False],
    )
    assert call_log == ["p1", "p2"], "p3 must never have been swept once headroom failed"
    evict_all.assert_not_called()


class _PlainEmbedder:
    """Stands in for a bare embedder passed instead of a ModelCache. It has no
    evict_all method at all, so any surviving call site would raise
    AttributeError rather than fail silently."""


@pytest.mark.asyncio
async def test_plain_embedder_without_evict_all_completes_the_sweep(
    monkeypatch, reset_auto_reindex,
):
    """The old code wrapped its eviction in `except AttributeError`, which
    would have hidden a stray call. Without that wrapper, an embedder lacking
    the method turns any surviving call into a visible failure, so a clean
    sweep here is real evidence that no call site remains."""
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelB", 1),
    ]
    _wire_common(monkeypatch, [planned], [{"__nonempty__": True}])
    monkeypatch.setattr(auto_reindex, "wait_for_system_headroom", AsyncMock(return_value=True))

    call_log = []

    async def fake_sweep_project(pid, entry, model_cache):
        call_log.append(pid)
        return pid == "p1"

    monkeypatch.setattr(auto_reindex, "_sweep_project", AsyncMock(side_effect=fake_sweep_project))

    plain_embedder = _PlainEmbedder()
    with pytest.raises(_StopSweep):
        await auto_reindex.auto_reindex_loop(lambda: plain_embedder)

    assert call_log == ["p1", "p2"], (
        "the sweep must cross the modelA to modelB boundary untouched"
    )


# ---------------------------------------------------------------------------
# Proof that the removal is a real change, and proof that the cap it leans on
# actually holds. Without the second of these, the first only shows that the
# sweep stopped evicting, not that residency is still bounded.
# ---------------------------------------------------------------------------

def _old_rule_boundaries_that_would_evict(models: list[str]) -> int:
    """A direct transcription of the removed boundary test, with no gating.
    Used only to show what the old code did on a given sweep order, never as a
    correctness reference for the new code."""
    last_model = None
    evictions = 0
    for model in models:
        if last_model is not None and model != last_model:
            evictions += 1
        last_model = model
    return evictions


def test_the_removed_rule_would_have_evicted_on_a_working_sweep():
    """The differential check. On the same input as the first test, the old
    rule crossed two boundaries and evicted at both, so the new assertion of
    zero evictions is a genuine divergence rather than a test that was always
    going to pass."""
    models = ["modelA", "modelA", "modelB", "modelB", "modelC"]
    assert _old_rule_boundaries_that_would_evict(models) == 2, (
        "sanity check on the transcription: two boundaries, A to B and B to C"
    )


def test_model_cache_caps_residency_without_any_help_from_the_sweep():
    """The safety net the removal depends on. If this ever stops holding, the
    sweep's eviction was load bearing after all and removing it was wrong."""
    from server.lang_router import ModelCache

    cache = ModelCache(max_resident=2)
    for name in ("m1", "m2", "m3", "m4"):
        cache._cache[name] = object()
        cache._enforce_max_resident(keep=name)
        assert len(cache._cache) <= 2, (
            f"residency reached {len(cache._cache)} after adding {name}, so "
            "_enforce_max_resident is not bounding the cache on its own"
        )

    assert cache.loaded_models() == ["m3", "m4"], (
        "the cap must drop least recently used first, keeping the newest two"
    )
