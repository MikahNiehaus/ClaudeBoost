"""Tests for gating auto_reindex_loop's model_cache.evict_all() on real work.

server/auto_reindex.py:auto_reindex_loop groups projects by embedding model
(server/reindex_unit.py:plan_sweep) and used to evict every resident model the
instant the model changed, with no regard for whether the group that just
finished actually did anything. A sweep that skipped every project because
another job held the index lock still threw away a model a concurrently
running /index-project was actively embedding with -- reloading
Salesforce/SFR-Embedding-Code-400M_R costs 135s, and this fired 4 times in
104 minutes during one real reindex (about 8.6 percent of its wall clock).

The fix adds a `group_did_work` accumulator, true only when at least one
project in the CURRENT model group actually held the lock and did real work
(`_sweep_project` returned True), reset at every group boundary. These tests
drive the real `auto_reindex_loop` coroutine end to end, with the registry,
the plan, the per-project sweep, and the model cache all faked, so the
assertions are about the loop's own control flow rather than about a
reimplementation of it.
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
    """Patch everything auto_reindex_loop touches except the eviction and
    accumulator logic under test.

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
# The production bug this diff fixes: every project skipped, group boundaries
# crossed, and nothing is evicted.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_skipped_across_several_group_boundaries_never_evicts(
    monkeypatch, reset_auto_reindex,
):
    """The exact production scenario: a manual /index-project holds the lock,
    every project returns False, several model group boundaries are crossed.
    evict_all must never be called."""
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


# ---------------------------------------------------------------------------
# Property 1: a group that did real work still evicts at the next boundary.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_that_did_work_evicts_at_the_next_boundary(monkeypatch, reset_auto_reindex):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelB", 1),
    ]
    evict_all, _ = await _run_sweeps(monkeypatch, [planned], proceeded_map={"p1": True})
    evict_all.assert_called_once()


# ---------------------------------------------------------------------------
# Property 3: the case a naive "gate on the immediately prior project alone"
# gets wrong -- an EARLIER project in the group did work, the LAST one before
# the boundary skipped, and the boundary must still evict.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_earlier_project_worked_last_one_skipped_still_evicts(
    monkeypatch, reset_auto_reindex,
):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),  # does work
        PlannedProject("p2", "/p2", "modelA", 1),  # skips, last in group
        PlannedProject("p3", "/p3", "modelB", 1),  # boundary
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned], proceeded_map={"p1": True, "p2": False},
    )
    assert call_log == ["p1", "p2", "p3"]
    evict_all.assert_called_once()


# ---------------------------------------------------------------------------
# Property 4: work in one group must not leak into the boundary out of the
# NEXT group. Group A worked, group B (a single project) did not; crossing
# out of B must not evict.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_did_work_resets_at_every_boundary(monkeypatch, reset_auto_reindex):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),  # works -> evicts at A/B boundary
        PlannedProject("p2", "/p2", "modelB", 1),  # skips
        PlannedProject("p3", "/p3", "modelC", 1),  # B/C boundary must NOT evict
    ]
    evict_all, _ = await _run_sweeps(
        monkeypatch, [planned], proceeded_map={"p1": True, "p2": False},
    )
    assert evict_all.call_count == 1, (
        "expected exactly one eviction (A->B); group B's idle boundary into C "
        "must not evict a second time"
    )


# ---------------------------------------------------------------------------
# Property 6: no eviction before the first group (last_model is None).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_eviction_on_the_first_group(monkeypatch, reset_auto_reindex):
    planned = [PlannedProject("p1", "/p1", "modelA", 1)]
    evict_all, _ = await _run_sweeps(monkeypatch, [planned], proceeded_map={"p1": True})
    evict_all.assert_not_called()


# ---------------------------------------------------------------------------
# Single project per model group must behave exactly like gating on the
# immediately prior project's `proceeded` alone -- the accumulator changes
# nothing for the degenerate case.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_singleton_groups_match_gating_on_proceeded_alone(monkeypatch, reset_auto_reindex):
    planned = [
        PlannedProject("p1", "/p1", "m1", 1),
        PlannedProject("p2", "/p2", "m2", 1),
        PlannedProject("p3", "/p3", "m3", 1),
    ]
    evict_all, _ = await _run_sweeps(
        monkeypatch, [planned], proceeded_map={"p1": True, "p2": False, "p3": True},
    )
    # m1->m2 boundary: gate reads p1's True -> evict.
    # m2->m3 boundary: gate reads p2's False -> no evict.
    # p3's True never reaches a boundary check (sweep ends after it).
    assert evict_all.call_count == 1


# ---------------------------------------------------------------------------
# The exception path. `proceeded` is assigned inside the try, and the new
# accumulator line sits after `if proceeded:` but still inside the same try.
# Confirm: (a) an exception on one project does not kill the sweep for the
# rest, (b) it does not silently corrupt group_did_work either direction.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exception_on_one_project_does_not_kill_the_rest_of_the_sweep(
    monkeypatch, reset_auto_reindex,
):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),  # raises
        PlannedProject("p2", "/p2", "modelA", 1),  # does real work
        PlannedProject("p3", "/p3", "modelB", 1),  # boundary
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned],
        proceeded_map={"p2": True},
        exception_map={"p1": RuntimeError("boom")},
    )
    assert call_log == ["p1", "p2", "p3"], (
        "an exception on p1 must not stop the loop from reaching p2 and p3 -- "
        "if `proceeded` referenced before assignment raised UnboundLocalError "
        "this would truncate here"
    )
    evict_all.assert_called_once()  # p2's real work still evicts at the A/B boundary


@pytest.mark.asyncio
async def test_exception_after_real_work_does_not_erase_group_did_work(
    monkeypatch, reset_auto_reindex,
):
    """p1 does real work, p2 raises before the accumulator line runs. The
    earlier work must still be remembered at the boundary -- the accumulator
    line sitting inside the try must not mean an exception downstream resets
    it, since the line never executes at all on that iteration (the
    exception is raised by the `await _sweep_project(...)` call itself,
    which is the right-hand side of the assignment, so control jumps straight
    to `except` without touching `group_did_work`)."""
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),  # does real work
        PlannedProject("p2", "/p2", "modelA", 1),  # raises
        PlannedProject("p3", "/p3", "modelB", 1),  # boundary
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned],
        proceeded_map={"p1": True},
        exception_map={"p2": RuntimeError("boom")},
    )
    assert call_log == ["p1", "p2", "p3"]
    evict_all.assert_called_once()


# ---------------------------------------------------------------------------
# `break` on pressure happens before the eviction check for the project that
# would have crossed the boundary. Confirm an abandoned sweep never evicts
# on the project it never got to.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_break_on_pressure_before_a_boundary_never_evicts(monkeypatch, reset_auto_reindex):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),
        PlannedProject("p2", "/p2", "modelA", 1),
        PlannedProject("p3", "/p3", "modelB", 1),  # would cross the boundary
    ]
    # Headroom ok for p1 and p2, pressured right as p3 is about to be
    # considered -- the break happens before p3's eviction check ever runs.
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [planned],
        proceeded_map={"p1": True, "p2": True},
        headroom_side_effect=[True, True, False],
    )
    assert call_log == ["p1", "p2"], "p3 must never have been swept once headroom failed"
    evict_all.assert_not_called()


# ---------------------------------------------------------------------------
# group_did_work must not leak across separate sweeps (separate `while True`
# iterations). It is reinitialised to False every sweep, so work recorded in
# sweep 1 must have no bearing on sweep 2's first boundary.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_did_work_does_not_leak_into_the_next_sweep(monkeypatch, reset_auto_reindex):
    sweep1 = [PlannedProject("s1p1", "/s1p1", "modelA", 1)]  # does work, single group, no boundary
    sweep2 = [
        PlannedProject("s2p1", "/s2p1", "modelA", 1),  # skips
        PlannedProject("s2p2", "/s2p2", "modelB", 1),  # boundary -- must not evict
    ]
    evict_all, call_log = await _run_sweeps(
        monkeypatch, [sweep1, sweep2],
        proceeded_map={"s1p1": True, "s2p1": False},
    )
    assert call_log == ["s1p1", "s2p1", "s2p2"]
    evict_all.assert_not_called()


# ---------------------------------------------------------------------------
# Differential check against the diff's own `-` lines: the OLD rule was a
# single unconditional `if last_model is not None and project.model !=
# last_model: evict_all()`, with no `group_did_work` at all. Simulating that
# exact removed rule against the same "all skipped" input the first test
# uses proves the old code really did have the bug the fix claims to close,
# and that the new code's behavior is a real divergence, not a no-op change.
# ---------------------------------------------------------------------------

def _old_rule_boundaries_that_would_evict(models: list[str]) -> int:
    """A direct transcription of the removed line
    (`if last_model is not None and project.model != last_model: evict_all()`),
    with no gating on whether the group did any work. Used only to prove the
    old code's behavior on the same scenario, never as a correctness
    reference for the new code."""
    last_model = None
    evictions = 0
    for model in models:
        if last_model is not None and model != last_model:
            evictions += 1
        last_model = model
    return evictions


# ---------------------------------------------------------------------------
# Property 8, second half: a plain embedder with no evict_all attribute must
# still be swallowed by `except AttributeError`, unchanged from before this
# diff, even when group_did_work is True and the eviction is actually
# attempted.
# ---------------------------------------------------------------------------

class _PlainEmbedder:
    """Stands in for a bare embedder passed instead of a ModelCache -- no
    evict_all method at all, so calling it raises AttributeError."""


@pytest.mark.asyncio
async def test_plain_embedder_without_evict_all_does_not_crash_the_sweep(
    monkeypatch, reset_auto_reindex,
):
    planned = [
        PlannedProject("p1", "/p1", "modelA", 1),  # does work -> eviction attempted at boundary
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
        "the AttributeError from evict_all() must be swallowed, not propagate "
        "and truncate the sweep"
    )


def test_old_ungated_rule_would_have_evicted_on_the_all_skipped_scenario():
    models = ["modelA", "modelA", "modelB", "modelB", "modelC"]
    assert _old_rule_boundaries_that_would_evict(models) == 2, (
        "sanity check on the transcription of the removed line: it must cross "
        "exactly two boundaries (A->B, B->C) regardless of whether any project "
        "in either group did work -- this is the bug the new group_did_work "
        "gate exists to close, confirmed against the real loop in "
        "test_all_skipped_across_several_group_boundaries_never_evicts"
    )
