"""reindex_project_fully must terminate even when it never gets the lock.

The index lock branch used to `continue` without touching `pauses`,
`stalled` or `errors`, so it bypassed every termination budget. With
acquire_index_lock mocked to always fail, the real function produced
180,000+ log lines and had to be force killed; rerun here it burned 93
seconds of CPU without returning.

The loop under test never awaits anything that yields, so asyncio.wait_for
cannot interrupt it. These tests therefore bound it from inside the mock,
by raising once the attempts exceed any legitimate budget. That way a
regression fails fast instead of hanging the suite.
"""

import asyncio
import sys
from pathlib import Path
from unittest import mock

import pytest

CLEAN_RAG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CLEAN_RAG))

import cli.reindex_batch as rb  # noqa: E402
from server.reindex_unit import Outcome, PlannedProject  # noqa: E402


class LoopDidNotTerminate(RuntimeError):
    """Raised by the test harness, never by production code."""


#: Any run needing more attempts than this has no working budget. Generous
#: enough that a correct implementation never reaches it.
ATTEMPT_CEILING = rb.MAX_STALLED_PAUSES * 4 + 50


@pytest.fixture
def project():
    return PlannedProject(pid="fake", path="C:/nowhere", size=1, model="m")


@pytest.fixture
def frozen_loop(monkeypatch):
    """Everything except the branch under test held still.

    Sleeps are removed so the test is instant, headroom always succeeds so the
    lock is the only thing blocking progress, and nothing else can end the
    loop.
    """
    monkeypatch.setattr(rb.time, "sleep", lambda _s: None)
    monkeypatch.setattr(rb, "wait_for_system_headroom", mock.AsyncMock(return_value=True))
    monkeypatch.setattr(rb, "stop_requested", lambda: False)
    monkeypatch.setattr(rb, "rss_mb", lambda: 1.0)
    monkeypatch.setattr(rb, "index_is_incomplete", lambda _p: False)
    monkeypatch.setattr(rb, "release_index_lock", lambda: None)


def bounded_lock(attempts, succeed=False):
    """acquire_index_lock that self destructs rather than spinning forever."""
    def acquire(_op):
        attempts.append(1)
        if len(attempts) > ATTEMPT_CEILING:
            raise LoopDidNotTerminate(
                f"still trying after {len(attempts)} lock attempts"
            )
        return succeed
    return acquire


class TestAPermanentlyHeldLockTerminates:
    def test_it_gives_up_instead_of_spinning(self, project, frozen_loop, monkeypatch):
        """bad-cop's exact scenario: the lock is held by a live process (the
        server's own hourly sweep) and never released."""
        attempts = []
        monkeypatch.setattr(rb, "acquire_index_lock", bounded_lock(attempts))

        outcome, _last = asyncio.run(
            rb.reindex_project_fully(project, cache=mock.Mock(), checkpoint=mock.Mock())
        )

        assert outcome is Outcome.GAVE_UP
        assert len(attempts) <= ATTEMPT_CEILING

    def test_it_gives_up_within_the_stall_budget(self, project, frozen_loop, monkeypatch):
        """Zero progress is being made, so the stall budget is what should end
        it. Bounding the attempts is what turns a hang into a deadline: at
        LOCK_WAIT_S apart, this is roughly 12 minutes of a lock it cannot get.
        """
        attempts = []
        monkeypatch.setattr(rb, "acquire_index_lock", bounded_lock(attempts))

        asyncio.run(
            rb.reindex_project_fully(project, cache=mock.Mock(), checkpoint=mock.Mock())
        )

        assert len(attempts) == rb.MAX_STALLED_PAUSES, (
            f"expected the stall budget to end it after "
            f"{rb.MAX_STALLED_PAUSES} attempts, got {len(attempts)}"
        )

    def test_the_log_does_not_run_away(self, project, frozen_loop, monkeypatch, capsys):
        """One line every 30 seconds forever is what turned a hang into
        180,000 log lines."""
        monkeypatch.setattr(rb, "acquire_index_lock", bounded_lock([]))

        asyncio.run(
            rb.reindex_project_fully(project, cache=mock.Mock(), checkpoint=mock.Mock())
        )

        lock_lines = [
            line for line in capsys.readouterr().out.splitlines()
            if "index lock held elsewhere" in line
        ]
        assert len(lock_lines) <= rb.MAX_STALLED_PAUSES, (
            f"{len(lock_lines)} lock-wait log lines"
        )
        assert "stalled" in lock_lines[0], (
            f"the wait line should show the budget it is counting against: "
            f"{lock_lines[0]!r}"
        )


class TestTheLockBranchDoesNotBreakTheHappyPath:
    def test_a_lock_that_frees_up_still_completes_the_project(
        self, project, frozen_loop, monkeypatch
    ):
        """The budget must bound failure without turning transient contention
        into a give up. The lock is busy for a few passes, then frees."""
        attempts = []
        busy_for = 3

        def acquire(_op):
            attempts.append(1)
            if len(attempts) > ATTEMPT_CEILING:
                raise LoopDidNotTerminate("no termination")
            return len(attempts) > busy_for

        monkeypatch.setattr(rb, "acquire_index_lock", acquire)
        monkeypatch.setattr(
            rb, "index_project", lambda *a, **k: {"files_indexed": 12},
        )

        outcome, last = asyncio.run(
            rb.reindex_project_fully(project, cache=mock.Mock(), checkpoint=mock.Mock())
        )

        assert outcome is Outcome.COMPLETED
        assert last == {"files_indexed": 12}
        assert len(attempts) == busy_for + 1

    def test_progress_resets_the_stall_counter(self, project, frozen_loop, monkeypatch):
        """The documented reset semantics have to survive counting lock waits
        against `stalled`: a pass that indexes files clears them.

        Alternating "lock busy" with a real indexing pass runs far past
        MAX_STALLED_PAUSES attempts without ever giving up.
        """
        attempts = []
        rounds = {"n": 0}

        def acquire(_op):
            attempts.append(1)
            if len(attempts) > ATTEMPT_CEILING:
                raise LoopDidNotTerminate("no termination")
            return len(attempts) % 2 == 0  # busy, free, busy, free, ...

        def index(*_a, **_k):
            rounds["n"] += 1
            return {"files_indexed": 5}

        monkeypatch.setattr(rb, "acquire_index_lock", acquire)
        monkeypatch.setattr(rb, "index_project", index)
        # Stay incomplete for many rounds so the loop keeps going.
        monkeypatch.setattr(
            rb, "index_is_incomplete",
            lambda _p: rounds["n"] < rb.MAX_STALLED_PAUSES + 5,
        )

        outcome, _last = asyncio.run(
            rb.reindex_project_fully(project, cache=mock.Mock(), checkpoint=mock.Mock())
        )

        assert outcome is Outcome.COMPLETED, (
            "steady progress was mistaken for a stall"
        )
        assert rounds["n"] > rb.MAX_STALLED_PAUSES


class TestTheTerminationInvariant:
    def test_every_continue_in_the_loop_advances_a_budget(self):
        """The invariant the docstring now states, checked against the source.

        Structural on purpose and narrow on purpose: the bug was a `continue`
        that skipped every counter, and no behavioural test can enumerate a
        branch that has not been written yet.
        """
        import ast
        import inspect
        import textwrap

        src = textwrap.dedent(inspect.getsource(rb.reindex_project_fully))
        loop = next(
            node for node in ast.walk(ast.parse(src)) if isinstance(node, ast.While)
        )

        counters = {"pauses", "stalled", "errors"}
        for branch in loop.body:
            if not isinstance(branch, ast.If):
                continue
            if not any(isinstance(n, ast.Continue) for n in ast.walk(branch)):
                continue
            bumped = {
                t.id
                for n in ast.walk(branch)
                if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name)
                for t in [n.target]
            }
            assert bumped & counters, (
                f"a branch at line {branch.lineno} of reindex_project_fully "
                f"continues without advancing any of {sorted(counters)}"
            )
