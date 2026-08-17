"""psutil's CPU sampling must be serialised across every call site.

Originally written by bad-cop to prove the defect: ``PressureCheckpoint``'s
docstring claimed the sampling was "serialised behind a lock because psutil's
global cpu_percent bookkeeping is not thread safe (giampaolo/psutil#1703)", but
the lock was released before ``sample_pressure()`` ran and was per instance
anyway. Two independent checkpoints (a manual /index-project racing the sweep)
were measured genuinely overlapping inside the sampling call, and
``auto_reindex.wait_for_system_headroom()`` reached ``sample_pressure()`` with
no lock at all.

Inverted here to assert the corrected contract: the psutil reads themselves are
mutually exclusive, whichever caller gets there. bad-cop's second test asserted
this by grepping the source of ``wait_for_system_headroom`` for the string
"Lock", which passes or fails on formatting rather than behaviour; it is
replaced below with two threads actually contending.
"""
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

CLEAN_RAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLEAN_RAG))

from server import resource_guard  # noqa: E402

HOLD_S = 0.05


class RecordingPsutil:
    """A psutil stand-in whose cpu_percent takes measurable time and records
    exactly when each thread was inside it."""

    def __init__(self, hold_s: float = HOLD_S, available_mb: float = 8000):
        self._hold = hold_s
        self._available_mb = available_mb
        self._guard = threading.Lock()
        self.timeline: list[tuple[str, str, float]] = []

    def cpu_percent(self, interval=None):
        with self._guard:
            self.timeline.append(("enter", threading.current_thread().name, time.monotonic()))
        time.sleep(self._hold)
        with self._guard:
            self.timeline.append(("exit", threading.current_thread().name, time.monotonic()))
        return 5.0

    def virtual_memory(self):
        return SimpleNamespace(available=self._available_mb * 1024 * 1024)


def _intervals(timeline):
    spans: dict[str, dict] = {}
    for kind, name, ts in timeline:
        spans.setdefault(name, {})[kind] = ts
    return spans


def _run_concurrently(workers):
    """Start every worker at the same instant and return once all finish."""
    barrier = threading.Barrier(len(workers))
    threads = []
    for name, fn in workers:
        def target(fn=fn, name=name):
            threading.current_thread().name = name
            barrier.wait()
            fn()

        t = threading.Thread(target=target, name=name)
        threads.append(t)
    started = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), f"{t.name} never finished; a lock is deadlocked"
    return time.monotonic() - started


def _assert_serialised(fake, elapsed, names):
    spans = _intervals(fake.timeline)
    assert set(spans) == set(names), f"expected both threads to sample: {fake.timeline}"

    a, b = (spans[n] for n in names)
    overlapped = a["enter"] < b["exit"] and b["enter"] < a["exit"]
    assert not overlapped, (
        f"two threads were inside psutil's cpu_percent at the same time, so "
        f"they consumed each other's baseline (giampaolo/psutil#1703): "
        f"{fake.timeline}"
    )
    # Non overlap alone can happen by luck if one thread simply finished first.
    # Serialised work takes both holds end to end; that is the real signal.
    assert elapsed >= 2 * HOLD_S * 0.9, (
        f"two {HOLD_S}s samples completed in {elapsed:.3f}s, which is too fast "
        f"to have been serialised"
    )


def test_two_independent_checkpoints_do_not_sample_at_the_same_time():
    """bad-cop's original attack. Two separate PressureCheckpoint instances are
    the real shape of a manual /index-project racing the sweep, and a per
    instance lock does nothing for them."""
    fake = RecordingPsutil()
    with patch.dict(sys.modules, {"psutil": fake}):
        cp_a = resource_guard.PressureCheckpoint(interval_s=0, max_percent=80, min_free_ram_mb=3072)
        cp_b = resource_guard.PressureCheckpoint(interval_s=0, max_percent=80, min_free_ram_mb=3072)
        fake.timeline.clear()  # drop the priming samples from construction

        elapsed = _run_concurrently([("worker-A", cp_a.pressure), ("worker-B", cp_b.pressure)])

    _assert_serialised(fake, elapsed, ["worker-A", "worker-B"])


def test_the_sweep_path_and_a_checkpoint_do_not_sample_at_the_same_time():
    """wait_for_system_headroom calls sample_pressure() directly (auto_reindex
    imports the same function object), bypassing every checkpoint. It must still
    be serialised against one."""
    from server import auto_reindex

    assert auto_reindex.sample_pressure is resource_guard.sample_pressure, (
        "auto_reindex no longer shares resource_guard's sampling function, so "
        "this test is no longer covering the sweep's real path"
    )

    fake = RecordingPsutil()
    with patch.dict(sys.modules, {"psutil": fake}):
        cp = resource_guard.PressureCheckpoint(interval_s=0, max_percent=80, min_free_ram_mb=3072)
        fake.timeline.clear()

        elapsed = _run_concurrently([
            ("checkpoint", cp.pressure),
            ("sweep", lambda: auto_reindex.sample_pressure(80, 3072)),
        ])

    _assert_serialised(fake, elapsed, ["checkpoint", "sweep"])


def test_priming_is_serialised_against_sampling():
    """prime_cpu_sampling() writes the same global baseline sample_pressure()
    reads, so a sweep priming while a worker samples corrupts the same state."""
    fake = RecordingPsutil()
    with patch.dict(sys.modules, {"psutil": fake}):
        elapsed = _run_concurrently([
            ("primer", resource_guard.prime_cpu_sampling),
            ("sampler", lambda: resource_guard.sample_pressure(80, 3072)),
        ])

    _assert_serialised(fake, elapsed, ["primer", "sampler"])


def test_sampling_still_reports_pressure_under_the_lock():
    """The lock must not change what gets reported. A guard that always returns
    None would pass every serialisation test above."""
    busy = RecordingPsutil(hold_s=0, available_mb=8000)
    busy.cpu_percent = lambda interval=None: 95.0
    with patch.dict(sys.modules, {"psutil": busy}):
        assert "CPU 95%" in resource_guard.sample_pressure(80, 3072)

    starved = RecordingPsutil(hold_s=0, available_mb=100)
    starved.cpu_percent = lambda interval=None: 5.0
    with patch.dict(sys.modules, {"psutil": starved}):
        assert "free RAM" in resource_guard.sample_pressure(80, 3072)


def test_a_slow_sampler_does_not_deadlock_repeat_calls():
    """The lock is taken and released per call, not held across the loop. If it
    leaked, the second call from the same thread would hang forever."""
    fake = RecordingPsutil(hold_s=0)
    with patch.dict(sys.modules, {"psutil": fake}):
        for _ in range(5):
            assert resource_guard.sample_pressure(80, 3072) is None


def test_wait_for_cpu_headroom_is_still_an_alias():
    from server import auto_reindex

    assert auto_reindex.wait_for_cpu_headroom is auto_reindex.wait_for_system_headroom


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s"]))
